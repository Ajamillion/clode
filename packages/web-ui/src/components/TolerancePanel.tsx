import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useOptimization } from '@stores/optimization.store'
import { buildToleranceRequest, fetchToleranceReport } from '@lib/tolerances'
import type { OptimizationRun, ToleranceMetricStats } from '@types/index'

function selectRun(selectedId: string | null, recent: OptimizationRun[], last: OptimizationRun | null) {
  if (selectedId) {
    const match = recent.find((run) => run.id === selectedId)
    if (match) return match
    if (last && last.id === selectedId) return last
  }
  return last ?? recent[0] ?? null
}

function formatPercent(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function formatDecibels(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(1)} dB`
}

function formatRange(stats: ToleranceMetricStats | undefined, unit: string) {
  if (!stats) return '—'
  return `${stats.p05.toFixed(1)} – ${stats.p95.toFixed(1)} ${unit}`
}

function riskLabel(rating: 'low' | 'moderate' | 'high') {
  switch (rating) {
    case 'high':
      return 'High risk'
    case 'moderate':
      return 'Moderate risk'
    default:
      return 'Low risk'
  }
}

export function TolerancePanel() {
  const selectedRunId = useOptimization((state) => state.selectedRunId)
  const recentRuns = useOptimization((state) => state.recentRuns)
  const lastRun = useOptimization((state) => state.lastRun)

  const run = useMemo(
    () => selectRun(selectedRunId, recentRuns, lastRun),
    [selectedRunId, recentRuns, lastRun],
  )

  const request = useMemo(() => buildToleranceRequest(run), [run])

  const {
    data: report,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: request ? ['tolerance-report', request.cacheKey] : ['tolerance-report', 'disabled'],
    queryFn: () => {
      if (!request) throw new Error('No tolerance request available')
      return fetchToleranceReport(request)
    },
    enabled: !!request,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })

  const headline = useMemo(() => {
    if (!report) return []
    const stats = report.metrics
    const spl = stats.max_spl_db
    const excursion = stats.max_cone_displacement_m
    const port = stats.max_port_velocity_ms
    const entries: { label: string; value: string; detail?: string }[] = []
    if (spl) {
      entries.push({
        label: 'Max SPL (mean)',
        value: `${spl.mean.toFixed(1)} dB`,
        detail: `90% span ${formatRange(spl, 'dB')}`,
      })
    }
    if (excursion) {
      entries.push({
        label: 'Cone displacement',
        value: `${(excursion.mean * 1000).toFixed(2)} mm`,
        detail: `90% span ${(excursion.p05 * 1000).toFixed(2)} – ${(excursion.p95 * 1000).toFixed(2)} mm`,
      })
    }
    if (port) {
      entries.push({
        label: 'Port velocity',
        value: `${port.mean.toFixed(1)} m/s`,
        detail: `90% span ${formatRange(port, 'm/s')}`,
      })
    }
    return entries
  }, [report])

  let body: JSX.Element
  if (!run || run.status !== 'succeeded') {
    body = <p className="tolerance__empty">Tolerance sweeps are available once an optimisation run completes.</p>
  } else if (!request) {
    body = <p className="tolerance__empty">Awaiting solver metrics before launching tolerance simulation.</p>
  } else if (isLoading) {
    body = <p className="tolerance__empty">Running Monte Carlo analysis…</p>
  } else if (isError) {
    body = (
      <div className="tolerance__error">
        <p>Unable to load tolerance snapshot.</p>
        <p className="tolerance__error-detail">{error instanceof Error ? error.message : String(error)}</p>
      </div>
    )
  } else if (!report) {
    body = <p className="tolerance__empty">No tolerance results yet.</p>
  } else {
    body = (
      <div className="tolerance__content">
        <div className={`tolerance__risk tolerance__risk--${report.risk_rating}`}>
          <span className="tolerance__risk-label">{riskLabel(report.risk_rating)}</span>
          <ul className="tolerance__risk-factors">
            {(report.risk_factors.length ? report.risk_factors : ['No risk factors were flagged.']).map((factor) => (
              <li key={factor}>{factor}</li>
            ))}
          </ul>
        </div>
        <div className="tolerance__grid">
          <div>
            <div className="tolerance__label">Excursion exceedance</div>
            <div className="tolerance__value">{formatPercent(report.excursion_exceedance_rate)}</div>
            <div className="tolerance__muted">Limit ratio {report.excursion_limit_ratio.toFixed(2)}×</div>
          </div>
          {report.port_velocity_limit_ms != null && (
            <div>
              <div className="tolerance__label">Port velocity exceedance</div>
              <div className="tolerance__value">{formatPercent(report.port_velocity_exceedance_rate)}</div>
              <div className="tolerance__muted">Limit {report.port_velocity_limit_ms.toFixed(1)} m/s</div>
            </div>
          )}
          <div>
            <div className="tolerance__label">Worst case SPL delta</div>
            <div className="tolerance__value">{formatDecibels(report.worst_case_spl_delta_db)}</div>
            <div className="tolerance__muted">Relative to baseline run</div>
          </div>
        </div>
        {headline.length > 0 && (
          <dl className="tolerance__highlights">
            {headline.map((entry) => (
              <div key={entry.label} className="tolerance__highlight">
                <dt>{entry.label}</dt>
                <dd>{entry.value}</dd>
                {entry.detail && <span>{entry.detail}</span>}
              </div>
            ))}
          </dl>
        )}
      </div>
    )
  }

  return (
    <aside className="tolerance">
      <header className="tolerance__header">
        <div>
          <span className="tolerance__title">Tolerance Snapshot</span>
          {run && <span className="tolerance__run">{run.id.slice(0, 6)}</span>}
        </div>
        <div className="tolerance__actions">
          <button
            type="button"
            className="tolerance__refresh"
            onClick={() => refetch()}
            disabled={!request || isFetching}
          >
            {isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>
      {body}
    </aside>
  )
}
