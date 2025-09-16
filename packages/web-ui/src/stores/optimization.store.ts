import { create } from 'zustand'
import type { IterationMetrics, OptParams } from '@types/index'
import { SolverWS, type ConnectionStatus } from '@lib/websocket'
import type {
  ConvergenceMessage,
  ConstraintViolationMessage,
  IterationMessage,
  TopologySwitchMessage
} from '@lib/protocol'

const iterationListeners = new Set<(data: IterationMetrics) => void>()

const HISTORY_WINDOW = 256

function clampHistory(values: number[], next?: number) {
  if (next === undefined) return values
  const updated = values.length >= HISTORY_WINDOW ? values.slice(values.length - HISTORY_WINDOW + 1) : [...values]
  updated.push(next)
  return updated
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
  startOptimization: (params: OptParams) => Promise<void>
  pauseOptimization: () => void
  onIterationUpdate: (cb: (d: IterationMetrics) => void) => () => void
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

export const useOptimization = create<OptimizationStore>((set, get) => ({
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
  onIterationUpdate: (cb) => {
    iterationListeners.add(cb)
    return () => iterationListeners.delete(cb)
  },
  startOptimization: async (params: OptParams) => {
    const existing = get().solverWS
    existing?.close()

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
      violations: []
    })

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
      await fetch((import.meta.env.VITE_API_BASE ?? '/api') + '/opt/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
      })
    } catch (error) {
      console.warn('Failed to notify optimizer start', error)
    }
  },
  pauseOptimization: () => {
    const ws = get().solverWS
    ws?.close()
    set({ solverWS: null, status: 'closed' })
  }
}))
