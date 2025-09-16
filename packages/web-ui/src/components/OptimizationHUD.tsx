import { useMemo, useState } from 'react'
import { useOptimization } from '@stores/optimization.store'
import type { OptParams } from '@types/index'
import type { ConnectionStatus } from '@lib/websocket'

const DEFAULT_PARAMS: OptParams = {
  targetSpl: 118,
  maxVolume: 65,
  weightLow: 1,
  weightMid: 0.6
}

const STATUS_COPY: Record<ConnectionStatus, string> = {
  idle: 'idle',
  connecting: 'connecting…',
  open: 'streaming',
  reconnecting: 'reconnecting…',
  closed: 'stopped'
}

function formatLoss(loss: number | null) {
  return loss == null ? '—' : loss.toFixed(4)
}

function formatGradient(grad: number | null) {
  if (grad == null) return '—'
  if (grad === 0) return '0'
  return grad.toExponential(2)
}

function formatTimestamp(ts: number | null) {
  if (!ts) return '—'
  const date = new Date(ts)
  return `${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
}

export function OptimizationHUD() {
  const {
    status,
    currentIteration,
    lastLoss,
    gradientNorm,
    topology,
    lossHistory,
    lastMessageAt,
    lastIteration,
    convergence,
    violations,
    startOptimization,
    pauseOptimization
  } = useOptimization()
  const [pending, setPending] = useState(false)

  const isActive = status === 'open' || status === 'connecting' || status === 'reconnecting'
  const hasConverged = (convergence?.converged ?? false) || (gradientNorm != null && gradientNorm < 1e-4 && currentIteration > 0)
  const iterationCount = convergence?.iterations ?? currentIteration
  const displayedLoss = convergence?.finalLoss ?? lastLoss
  const violationCount = violations.length
  const latestViolation = violations[violationCount - 1]

  const sparklinePath = useMemo(() => {
    if (lossHistory.length < 2) return ''
    const width = 120
    const height = 32
    const offset = 2
    const values = lossHistory.slice(-40)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1
    return values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * (width - offset * 2) + offset
        const y = height - offset - ((v - min) / range) * (height - offset * 2)
        return `${x},${y}`
      })
      .join(' ')
  }, [lossHistory])

  const solution = convergence?.solution as Record<string, unknown> | undefined
  const solutionSpl = typeof solution?.spl === 'number' ? (solution.spl as number) : undefined
  const solutionSplPeak = typeof solution?.splPeak === 'number' ? (solution.splPeak as number) : undefined
  const latestSpl = solutionSpl ?? solutionSplPeak ?? lastIteration?.metrics?.spl ?? lastIteration?.metrics?.spl_peak
  const iterationStamp = formatTimestamp(lastMessageAt)

  const handleStart = async () => {
    setPending(true)
    try {
      await startOptimization(DEFAULT_PARAMS)
    } catch (error) {
      console.error('Failed to start optimization session', error)
    } finally {
      setPending(false)
    }
  }

  return (
    <aside className="hud">
      <header>
        <span className="hud__status" data-testid="connection-status">
          {STATUS_COPY[status]}
        </span>
        <span className={`hud__badge ${hasConverged ? 'hud__badge--good' : 'hud__badge--progress'}`} data-testid="convergence-indicator">
          {hasConverged ? 'converged' : isActive ? 'optimizing…' : 'standing by'}
        </span>
      </header>

      <div className="hud__row">
        <div>
          <div className="hud__label">Iteration</div>
          <div className="hud__value" data-testid="iteration-count">{iterationCount}</div>
        </div>
        <div>
          <div className="hud__label">Loss</div>
          <div className="hud__value" data-testid="latest-loss">{formatLoss(displayedLoss)}</div>
        </div>
        <div>
          <div className="hud__label">Gradient</div>
          <div className="hud__value" data-testid="gradient-norm">{formatGradient(gradientNorm)}</div>
        </div>
      </div>

      <div className="hud__row">
        <div>
          <div className="hud__label">Topology</div>
          <div className="hud__value" data-testid="topology-tag">{topology ?? '—'}</div>
        </div>
        <div>
          <div className="hud__label">Last update</div>
          <div className="hud__value">{iterationStamp}</div>
        </div>
        <div>
          <div className="hud__label">Peak SPL</div>
          <div className="hud__value" data-testid="final-spl">
            {latestSpl != null ? latestSpl.toFixed(1) : '—'}
          </div>
        </div>
        <div>
          <div className="hud__label">Violations</div>
          <div className="hud__value" data-testid="violation-count">{violationCount}</div>
          {latestViolation && (
            <div className="hud__muted">{latestViolation.constraint}{' '}
              {typeof latestViolation.severity === 'number' ? `• ${(latestViolation.severity * 100).toFixed(0)}%` : ''}
            </div>
          )}
        </div>
      </div>

      <div className="hud__spark">
        <svg width="120" height="32" role="img" aria-label="Loss trend">
          <polyline points={sparklinePath} fill="none" stroke="#22d3ee" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      <footer className="hud__actions">
        <button
          type="button"
          className="hud__button"
          data-testid="start-optimization"
          onClick={handleStart}
          disabled={pending || isActive}
        >
          {pending ? 'Starting…' : 'Start'}
        </button>
        <button
          type="button"
          className="hud__button hud__button--secondary"
          data-testid="pause-optimization"
          onClick={pauseOptimization}
          disabled={!isActive}
        >
          Pause
        </button>
      </footer>
    </aside>
  )
}
