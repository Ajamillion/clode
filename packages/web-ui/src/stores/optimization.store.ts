import { create } from 'zustand'
import type {
  IterationMetrics,
  OptParams,
  OptimizationRun,
  OptimizationRunResult,
  RunStats,
  RunStatus,
  RunStatusCounts
} from '@types/index'
import { SolverWS, type ConnectionStatus } from '@lib/websocket'
import type {
  ConvergenceMessage,
  ConstraintViolationMessage,
  IterationMessage,
  TopologySwitchMessage
} from '@lib/protocol'

const iterationListeners = new Set<(data: IterationMetrics) => void>()
const RUN_STATUSES: RunStatus[] = ['queued', 'running', 'succeeded', 'failed']

const HISTORY_WINDOW = 256
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'
const POLL_INTERVAL_MS = 2000
const RUNS_POLL_INTERVAL_MS = 10000

let pollTimer: ReturnType<typeof setInterval> | null = null
let runsPollTimer: ReturnType<typeof setInterval> | null = null

function clearRunPoll() {
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function clearRunHistoryPoll() {
  if (runsPollTimer != null) {
    clearInterval(runsPollTimer)
    runsPollTimer = null
  }
}

function clampHistory(values: number[], next?: number) {
  if (next === undefined) return values
  const updated = values.length >= HISTORY_WINDOW ? values.slice(values.length - HISTORY_WINDOW + 1) : [...values]
  updated.push(next)
  return updated
}

function normaliseNumberRecord(value: unknown): Record<string, number> | undefined {
  if (!value || typeof value !== 'object') return undefined
  const record: Record<string, number> = {}
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    const num = Number(raw)
    if (!Number.isNaN(num)) {
      record[key] = num
    }
  }
  return Object.keys(record).length ? record : undefined
}

function normaliseSummaryRecord(value: unknown): Record<string, number | null> | undefined {
  if (!value || typeof value !== 'object') return undefined
  const record: Record<string, number | null> = {}
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    if (raw === null) {
      record[key] = null
    } else {
      const num = Number(raw)
      if (!Number.isNaN(num)) {
        record[key] = num
      }
    }
  }
  return Object.keys(record).length ? record : undefined
}

function normaliseResponseRecord(value: unknown): Record<string, number[]> | undefined {
  if (!value || typeof value !== 'object') return undefined
  const record: Record<string, number[]> = {}
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    if (!Array.isArray(raw)) continue
    const arr = raw.map((entry) => Number(entry)).filter((num) => !Number.isNaN(num))
    if (arr.length) {
      record[key] = arr
    }
  }
  return Object.keys(record).length ? record : undefined
}

function normaliseHistory(entries: unknown): IterationMetrics[] | undefined {
  if (!Array.isArray(entries)) return undefined
  const mapped = entries
    .map((entry) => {
      if (!entry || typeof entry !== 'object') return undefined
      const iter = Number((entry as Record<string, unknown>).iter ?? 0)
      if (Number.isNaN(iter)) return undefined
      const loss = (entry as Record<string, unknown>).loss
      const grad = (entry as Record<string, unknown>).gradNorm
      const metrics = normaliseNumberRecord((entry as Record<string, unknown>).metrics)
      return {
        iter,
        loss: loss != null ? Number(loss) : undefined,
        gradNorm: grad != null ? Number(grad) : undefined,
        metrics
      } satisfies IterationMetrics
    })
    .filter((item): item is IterationMetrics => item !== undefined)
  return mapped.length ? mapped : undefined
}

function normaliseRunResult(raw: unknown): OptimizationRunResult | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const obj = raw as Record<string, unknown>
  const history = normaliseHistory(obj.history)
  const convergenceRaw = obj.convergence as Record<string, unknown> | undefined
  const convergence = convergenceRaw
    ? {
        converged: convergenceRaw.converged as boolean | undefined,
        iterations: convergenceRaw.iterations as number | undefined,
        finalLoss: convergenceRaw.finalLoss as number | undefined,
        cpuTime: convergenceRaw.cpuTime as number | undefined,
        solution: convergenceRaw.solution as Record<string, unknown> | undefined
      }
    : undefined
  const alignment = typeof obj.alignment === 'string' ? obj.alignment : undefined
  return {
    history,
    convergence,
    summary: normaliseSummaryRecord(obj.summary),
    response: normaliseResponseRecord(obj.response),
    metrics: normaliseNumberRecord(obj.metrics),
    alignment
  }
}

function normaliseRun(raw: unknown): OptimizationRun | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const id = obj.id
  if (!id) return null
  return {
    id: String(id),
    status: (obj.status as string | undefined) ?? 'queued',
    created_at: Number(obj.created_at ?? Date.now() / 1000),
    updated_at: Number(obj.updated_at ?? Date.now() / 1000),
    params: (obj.params && typeof obj.params === 'object' ? (obj.params as Record<string, unknown>) : {}),
    result: normaliseRunResult(obj.result),
    error: typeof obj.error === 'string' ? obj.error : null
  }
}

function normaliseStatusCounts(raw: unknown): RunStats | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const countsRaw = obj.counts as Record<string, unknown> | undefined
  if (!countsRaw || typeof countsRaw !== 'object') return null
  const counts: RunStatusCounts = {}
  for (const status of RUN_STATUSES) {
    const value = countsRaw[status]
    const num = Number(value)
    if (!Number.isNaN(num)) {
      counts[status] = num
    }
  }
  const totalRaw = obj.total
  const total = Number(totalRaw)
  return {
    counts,
    total: Number.isFinite(total) ? total : 0
  }
}

type OptimizationStore = {
  status: ConnectionStatus
  currentIteration: number
  lastLoss: number | null
  gradientNorm: number | null
  topology: string | null
  lossHistory: number[]
  gradientHistory: number[]
  lastMessageAt: number | null
  lastIteration: IterationMetrics | null
  convergence: ConvergenceMessage | null
  violations: ConstraintViolationMessage[]
  solverWS: SolverWS | null
  activeRunId: string | null
  lastRun: OptimizationRun | null
  recentRuns: OptimizationRun[]
  runStats: RunStats | null
  selectedRunId: string | null
  startOptimization: (params: OptParams) => Promise<void>
  pauseOptimization: () => void
  refreshRuns: () => Promise<void>
  onIterationUpdate: (cb: (d: IterationMetrics) => void) => () => void
  selectRun: (id: string | null) => void
}

function toIterationMetrics(data: IterationMessage, fallbackIter: number): IterationMetrics {
  return {
    iter: data.iter ?? fallbackIter,
    loss: data.loss,
    gradNorm: data.gradNorm,
    topology: data.topology,
    timestamp: data.timestamp ?? Date.now(),
    metrics: data.metrics
  }
}

function handleTopologySwitch(data: TopologySwitchMessage | undefined, current: string | null) {
  if (!data) return current
  return data.to ?? current
}

export const useOptimization = create<OptimizationStore>((set, get) => {
  const scheduleRunPolling = (runId: string) => {
    clearRunPoll()
    pollTimer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/opt/${runId}`)
        if (!response.ok) {
          return
        }
        const payload = normaliseRun(await response.json())
        if (!payload) return
        set((state) => {
          let lossHistory = state.lossHistory
          let gradientHistory = state.gradientHistory
          let currentIteration = state.currentIteration
          let lastIteration = state.lastIteration
          let lastLoss = state.lastLoss
          let gradientNorm = state.gradientNorm

          const runHistory = payload.result?.history
          if (runHistory?.length) {
            const newEntries = runHistory.filter((entry) => entry.iter > state.currentIteration)
            if (newEntries.length) {
              for (const entry of newEntries) {
                lossHistory = clampHistory(lossHistory, entry.loss)
                gradientHistory = clampHistory(gradientHistory, entry.gradNorm)
              }
              const latest = newEntries[newEntries.length - 1]
              currentIteration = latest.iter
              lastIteration = {
                ...latest,
                timestamp: Date.now(),
                topology: latest.topology ?? state.topology
              }
              if (latest.loss != null) {
                lastLoss = latest.loss
              }
              if (latest.gradNorm != null) {
                gradientNorm = latest.gradNorm
              }
            }
          }

          const convergence = payload.result?.convergence
            ? { ...state.convergence, ...payload.result.convergence }
            : state.convergence

          const selectedRunId = state.selectedRunId ?? payload.id

          return {
            lossHistory,
            gradientHistory,
            currentIteration,
            lastIteration,
            lastLoss,
            gradientNorm,
            lastMessageAt: Math.round(payload.updated_at * 1000),
            convergence,
            lastRun: payload,
            selectedRunId
          }
        })

        if (payload.status === 'succeeded' || payload.status === 'failed') {
          clearRunPoll()
        }
      } catch (error) {
        console.warn('Failed to poll optimisation run', error)
      }
    }, POLL_INTERVAL_MS)
  }

  const resetState = () =>
    set({
      currentIteration: 0,
      lastLoss: null,
      gradientNorm: null,
      lossHistory: [],
      gradientHistory: [],
      lastIteration: null,
      topology: null,
      lastMessageAt: null,
      convergence: null,
      violations: [],
      activeRunId: null,
      lastRun: null,
      selectedRunId: null
    })

  const fetchRunHistory = async () => {
    try {
      const response = await fetch(`${API_BASE}/opt/runs?limit=20`)
      if (!response.ok) return
      const payload = await response.json().catch(() => null)
      if (!payload || typeof payload !== 'object') return
      const runsRaw = (payload as Record<string, unknown>).runs
      if (!Array.isArray(runsRaw)) return
      const runs = runsRaw
        .map((entry) => normaliseRun(entry))
        .filter((run): run is OptimizationRun => run !== null)
      set((state) => {
        let selectedRunId = state.selectedRunId
        if (selectedRunId) {
          const exists = runs.some((run) => run.id === selectedRunId)
          if (!exists) {
            selectedRunId = runs[0]?.id ?? null
          }
        } else if (runs.length) {
          selectedRunId = runs[0]?.id ?? null
        }

        return {
          recentRuns: runs,
          selectedRunId
        }
      })
    } catch (error) {
      if (import.meta.env?.DEV) {
        console.warn('Failed to refresh optimisation runs', error)
      }
    }
  }

  const fetchRunStats = async () => {
    try {
      const response = await fetch(`${API_BASE}/opt/stats`)
      if (!response.ok) return
      const payload = await response.json().catch(() => null)
      const stats = normaliseStatusCounts(payload)
      if (stats) {
        set({ runStats: stats })
      }
    } catch (error) {
      if (import.meta.env?.DEV) {
        console.warn('Failed to refresh optimisation stats', error)
      }
    }
  }

  const ensureRunsPolling = () => {
    if (typeof window === 'undefined') return
    if (runsPollTimer != null) return
    runsPollTimer = window.setInterval(() => {
      void fetchRunHistory()
      void fetchRunStats()
    }, RUNS_POLL_INTERVAL_MS)
  }

  const refreshRuns = async () => {
    await Promise.all([fetchRunHistory(), fetchRunStats()])
    ensureRunsPolling()
  }

  return {
    status: 'idle',
    currentIteration: 0,
    lastLoss: null,
    gradientNorm: null,
    topology: null,
    lossHistory: [],
    gradientHistory: [],
    lastMessageAt: null,
    lastIteration: null,
    convergence: null,
    violations: [],
    solverWS: null,
    activeRunId: null,
    lastRun: null,
    recentRuns: [],
    runStats: null,
    selectedRunId: null,
    onIterationUpdate: (cb) => {
      iterationListeners.add(cb)
      return () => iterationListeners.delete(cb)
    },
    refreshRuns,
    selectRun: (id) => set({ selectedRunId: id }),
    startOptimization: async (params: OptParams) => {
      const existing = get().solverWS
      existing?.close()
      clearRunPoll()
      resetState()

      const url = import.meta.env.VITE_SOLVER_WS_URL || 'ws://localhost:8787/ws'
      const ws = new SolverWS(url, {
        onIteration: (data) => {
          const iterMetrics = toIterationMetrics(data, get().currentIteration + 1)
          iterationListeners.forEach((listener) => listener(iterMetrics))
          set((state) => ({
            currentIteration: iterMetrics.iter,
            lastLoss: iterMetrics.loss ?? state.lastLoss,
            gradientNorm: iterMetrics.gradNorm ?? state.gradientNorm,
            topology: iterMetrics.topology ?? state.topology,
            lossHistory: clampHistory(state.lossHistory, iterMetrics.loss),
            gradientHistory: clampHistory(state.gradientHistory, iterMetrics.gradNorm),
            lastMessageAt: iterMetrics.timestamp,
            lastIteration: iterMetrics
          }))
        },
        onTopology: (data) => {
          set((state) => ({ topology: handleTopologySwitch(data, state.topology) }))
        },
        onConvergence: (data) => {
          set({ convergence: data })
        },
        onViolation: (data) => {
          set((state) => ({ violations: [...state.violations, data] }))
        },
        onStatusChange: (status) => set({ status })
      })

      ws.connect()

      set({ solverWS: ws, status: ws.connectionStatus })

      try {
        const response = await fetch(`${API_BASE}/opt/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params)
        })
        if (response.ok) {
          const payload = await response.json().catch(() => null)
          const run = normaliseRun(payload)
          if (run) {
            set({ activeRunId: run.id, lastRun: run, selectedRunId: run.id })
            scheduleRunPolling(run.id)
          }
        } else {
          console.warn('Failed to notify optimizer start', response.status)
        }
      } catch (error) {
        console.warn('Failed to notify optimizer start', error)
      }

      ensureRunsPolling()
      void fetchRunHistory()
      void fetchRunStats()
    },
    pauseOptimization: () => {
      clearRunPoll()
      clearRunHistoryPoll()
      const wsInstance = get().solverWS
      wsInstance?.close()
      set({ solverWS: null, status: 'closed', activeRunId: null })
    }
  }
})
