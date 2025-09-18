import { useEffect, useMemo } from 'react'
import { useOptimization } from '@stores/optimization.store'
import type { OptimizationRun, RunStatus } from '@types/index'

const STATUS_LABEL: Record<RunStatus, string> = {
  queued: 'queued',
  running: 'running',
  succeeded: 'succeeded',
  failed: 'failed'
}

const STATUS_ORDER: RunStatus[] = ['running', 'queued', 'succeeded', 'failed']

function formatRelative(seconds: number | null | undefined) {
  if (!seconds) return '—'
  const ms = seconds * 1000
  const delta = Date.now() - ms
  if (delta < 0) return 'just now'
  const minutes = Math.floor(delta / 60000)
  if (minutes <= 1) return 'moments ago'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function truncate(id: string) {
  return id.length <= 8 ? id : `${id.slice(0, 4)}…${id.slice(-4)}`
}

function summariseRun(run: OptimizationRun) {
  const status = run.status
  const alignment = run.result?.alignment
  const finalLoss = run.result?.convergence?.finalLoss
  const iterations = run.result?.convergence?.iterations
  return {
    status,
    alignment,
    finalLoss: typeof finalLoss === 'number' ? finalLoss : null,
    iterations: typeof iterations === 'number' ? iterations : null
  }
}

export function RunHistoryPanel() {
  const recentRuns = useOptimization((state) => state.recentRuns)
  const runStats = useOptimization((state) => state.runStats)
  const refreshRuns = useOptimization((state) => state.refreshRuns)
  const status = useOptimization((state) => state.status)
  const activeRunId = useOptimization((state) => state.activeRunId)
  const selectedRunId = useOptimization((state) => state.selectedRunId)
  const selectRun = useOptimization((state) => state.selectRun)

  useEffect(() => {
    void refreshRuns()
  }, [refreshRuns])

  useEffect(() => {
    if (!selectedRunId && activeRunId) {
      selectRun(activeRunId)
    }
  }, [activeRunId, selectedRunId, selectRun])

  useEffect(() => {
    if (status === 'open' || status === 'connecting' || status === 'reconnecting') {
      void refreshRuns()
    }
  }, [status, refreshRuns])

  const selectedRun = useMemo(
    () =>
      recentRuns.find((run) => run.id === selectedRunId) ?? null,
    [recentRuns, selectedRunId]
  )

  const totalRuns = runStats?.total ?? recentRuns.length
  const counts = runStats?.counts ?? {}

  return (
    <aside className="run-history">
      <header className="run-history__header">
        <div>
          <span className="run-history__title">Run history</span>
          <span className="run-history__count">{totalRuns}</span>
        </div>
        <div className="run-history__stats">
          {STATUS_ORDER.map((state) => (
            <span key={state} className={`run-history__badge run-history__badge--${state}`}>
              {STATUS_LABEL[state]} · {counts?.[state] ?? 0}
            </span>
          ))}
        </div>
      </header>

      <div className="run-history__list" role="list">
        {recentRuns.length === 0 ? (
          <div className="run-history__empty">No runs yet – launch an optimisation to populate history.</div>
        ) : (
          recentRuns.map((run) => {
            const meta = summariseRun(run)
            const isSelected = run.id === selectedRunId
            return (
              <button
                key={run.id}
                type="button"
                className={`run-history__item${isSelected ? ' run-history__item--active' : ''}`}
                onClick={() => selectRun(run.id)}
              >
                <div className="run-history__item-top">
                  <span className="run-history__item-id">{truncate(run.id)}</span>
                  <span className={`run-history__status run-history__status--${run.status}`}>
                    {STATUS_LABEL[run.status]}
                  </span>
                </div>
                <div className="run-history__item-meta">
                  <span>{formatRelative(run.updated_at)}</span>
                  {meta.alignment && <span>{meta.alignment}</span>}
                  {meta.iterations != null && <span>{meta.iterations} iters</span>}
                  {meta.finalLoss != null && <span>loss {meta.finalLoss.toFixed(3)}</span>}
                </div>
              </button>
            )
          })
        )}
      </div>

      {selectedRun && (
        <div className="run-history__details">
          <div className="run-history__details-title">Selected run</div>
          <dl>
            <div>
              <dt>Status</dt>
              <dd>{STATUS_LABEL[selectedRun.status]}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatRelative(selectedRun.created_at)}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{formatRelative(selectedRun.updated_at)}</dd>
            </div>
            {selectedRun.result?.alignment && (
              <div>
                <dt>Alignment</dt>
                <dd>{selectedRun.result.alignment}</dd>
              </div>
            )}
            {selectedRun.result?.metrics?.achieved_spl_db && (
              <div>
                <dt>Achieved SPL</dt>
                <dd>{selectedRun.result.metrics.achieved_spl_db.toFixed(1)} dB</dd>
              </div>
            )}
            {selectedRun.error && (
              <div>
                <dt>Error</dt>
                <dd>{selectedRun.error}</dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </aside>
  )
}
