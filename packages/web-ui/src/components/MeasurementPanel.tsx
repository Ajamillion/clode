import { useMemo, useRef, type ChangeEventHandler } from 'react'
import { useMeasurement } from '@stores/measurement.store'
import { useOptimization } from '@stores/optimization.store'
import type { MeasurementTrace, OptimizationRun } from '@types/index'

const SOURCE_LABEL: Record<string, string> = {
  synthetic: 'Synthetic preview',
  upload: 'Uploaded file',
}

function selectRun(selectedId: string | null, recent: OptimizationRun[], last: OptimizationRun | null) {
  if (selectedId) {
    const match = recent.find((run) => run.id === selectedId)
    if (match) return match
    if (last && last.id === selectedId) return last
  }
  return last ?? recent[0] ?? null
}

function formatFrequency(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  if (value >= 1000) return `${(value / 1000).toFixed(2)} kHz`
  return `${value.toFixed(1)} Hz`
}

function formatDecibel(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(2)} dB`
}

function formatVoltage(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(2)} V`
}

function formatRelative(timestamp: number | null) {
  if (!timestamp) return '—'
  const delta = Date.now() - timestamp
  if (delta < 30_000) return 'just now'
  const minutes = Math.floor(delta / 60_000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function summariseMeasurement(trace: MeasurementTrace | null) {
  if (!trace || !trace.frequency_hz.length) return null
  const points = trace.frequency_hz.length
  let minFreq = Number.POSITIVE_INFINITY
  let maxFreq = Number.NEGATIVE_INFINITY
  for (const value of trace.frequency_hz) {
    if (!Number.isFinite(value)) continue
    if (value < minFreq) minFreq = value
    if (value > maxFreq) maxFreq = value
  }
  let splMin: number | null = null
  let splMax: number | null = null
  if (trace.spl_db && trace.spl_db.length === points) {
    for (const value of trace.spl_db) {
      if (!Number.isFinite(value)) continue
      splMin = splMin == null ? value : Math.min(splMin, value)
      splMax = splMax == null ? value : Math.max(splMax, value)
    }
  }
  return {
    points,
    minFreq: Number.isFinite(minFreq) ? minFreq : null,
    maxFreq: Number.isFinite(maxFreq) ? maxFreq : null,
    splMin,
    splMax,
  }
}

export function MeasurementPanel() {
  const selectedRunId = useOptimization((state) => state.selectedRunId)
  const recentRuns = useOptimization((state) => state.recentRuns)
  const lastRun = useOptimization((state) => state.lastRun)

  const run = useMemo(() => selectRun(selectedRunId, recentRuns, lastRun), [selectedRunId, recentRuns, lastRun])

  const preview = useMeasurement((state) => state.preview)
  const previewSource = useMeasurement((state) => state.previewSource)
  const comparison = useMeasurement((state) => state.comparison)
  const lastRunId = useMeasurement((state) => state.lastRunId)
  const lastComparedAt = useMeasurement((state) => state.lastComparedAt)
  const loading = useMeasurement((state) => state.loading)
  const error = useMeasurement((state) => state.error)
  const previewFromFile = useMeasurement((state) => state.previewFromFile)
  const generateSynthetic = useMeasurement((state) => state.generateSynthetic)
  const compareWithRun = useMeasurement((state) => state.compareWithRun)
  const clearComparison = useMeasurement((state) => state.clearComparison)

  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const measurementSummary = useMemo(() => summariseMeasurement(preview), [preview])

  const statsEntries = useMemo(() => {
    const stats = comparison?.stats
    if (!stats) return []
    const entries: { label: string; value: string }[] = []
    if (stats.spl_rmse_db != null) {
      entries.push({ label: 'SPL RMSE', value: formatDecibel(stats.spl_rmse_db) })
    }
    if (stats.spl_bias_db != null) {
      entries.push({ label: 'SPL bias', value: formatDecibel(stats.spl_bias_db) })
    }
    if (stats.max_spl_delta_db != null) {
      entries.push({ label: 'Worst delta', value: formatDecibel(stats.max_spl_delta_db) })
    }
    if (stats.phase_rmse_deg != null) {
      entries.push({ label: 'Phase RMSE', value: `${stats.phase_rmse_deg.toFixed(2)}°` })
    }
    if (stats.impedance_mag_rmse_ohm != null) {
      entries.push({ label: 'Impedance RMSE', value: `${stats.impedance_mag_rmse_ohm.toFixed(2)} Ω` })
    }
    return entries
  }, [comparison])

  const summaryEntries = useMemo(() => {
    const summary = comparison?.summary
    if (!summary) return []
    const entries: { label: string; value: string }[] = []
    if (summary.max_spl_db != null) {
      entries.push({ label: 'Predicted SPL', value: formatDecibel(summary.max_spl_db) })
    }
    if (summary.safe_drive_voltage_v != null) {
      entries.push({ label: 'Safe drive', value: formatVoltage(summary.safe_drive_voltage_v) })
    }
    if (summary.excursion_headroom_db != null) {
      entries.push({ label: 'Excursion headroom', value: formatDecibel(summary.excursion_headroom_db) })
    }
    if (summary.fb_hz != null) {
      entries.push({ label: 'Fb', value: formatFrequency(summary.fb_hz) })
    }
    return entries
  }, [comparison])

  const canCompare = !!preview && run?.status === 'succeeded'

  const handleFileChange: ChangeEventHandler<HTMLInputElement> = (event) => {
    const file = event.currentTarget.files?.[0]
    if (file) {
      void previewFromFile(file)
    }
    event.currentTarget.value = ''
  }

  let body: JSX.Element
  if (!run || run.status !== 'succeeded') {
    body = (
      <div className="measurement__content">
        {error && <div className="measurement__error">{error}</div>}
        <p className="measurement__empty">Measurement comparisons activate once an optimisation run completes.</p>
      </div>
    )
  } else {
    body = (
      <div className="measurement__content">
        {error && <div className="measurement__error">{error}</div>}
        <section className="measurement__section">
          <header className="measurement__section-title">Measurement preview</header>
          {preview ? (
            <dl className="measurement__grid">
              <div>
                <dt>Points</dt>
                <dd>{measurementSummary?.points ?? preview.frequency_hz.length}</dd>
              </div>
              <div>
                <dt>Frequency span</dt>
                <dd>
                  {formatFrequency(measurementSummary?.minFreq ?? null)}
                  <span> → {formatFrequency(measurementSummary?.maxFreq ?? null)}</span>
                </dd>
              </div>
              <div>
                <dt>SPL window</dt>
                <dd>
                  {measurementSummary?.splMin != null ? formatDecibel(measurementSummary.splMin) : '—'}
                  <span> → {measurementSummary?.splMax != null ? formatDecibel(measurementSummary.splMax) : '—'}</span>
                </dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd>{previewSource ? SOURCE_LABEL[previewSource] ?? previewSource : '—'}</dd>
              </div>
            </dl>
          ) : (
            <p className="measurement__empty">Generate a synthetic measurement or upload a Klippel/REW capture to compare.</p>
          )}
        </section>
        <section className="measurement__section">
          <header className="measurement__section-title">Fit results</header>
          {loading ? (
            <p className="measurement__empty">Comparing measurement to solver prediction…</p>
          ) : comparison ? (
            <div className="measurement__results">
              <dl className="measurement__grid">
                <div>
                  <dt>Samples</dt>
                  <dd>{comparison.stats?.sample_count ?? measurementSummary?.points ?? '—'}</dd>
                </div>
                <div>
                  <dt>Compared run</dt>
                  <dd>{lastRunId ? `${lastRunId.slice(0, 6)}…` : run.id.slice(0, 6)}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{formatRelative(lastComparedAt)}</dd>
                </div>
              </dl>
              {(statsEntries.length > 0 || summaryEntries.length > 0) && (
                <div className="measurement__highlights">
                  {statsEntries.map((entry) => (
                    <div key={entry.label}>
                      <dt>{entry.label}</dt>
                      <dd>{entry.value}</dd>
                    </div>
                  ))}
                  {summaryEntries.map((entry) => (
                    <div key={entry.label}>
                      <dt>{entry.label}</dt>
                      <dd>{entry.value}</dd>
                    </div>
                  ))}
                </div>
              )}
              <button type="button" className="measurement__clear" onClick={() => clearComparison()}>
                Clear comparison
              </button>
            </div>
          ) : (
            <p className="measurement__empty">Run a comparison to surface SPL and impedance deltas against the solver baseline.</p>
          )}
        </section>
      </div>
    )
  }

  return (
    <aside className="measurement">
      <header className="measurement__header">
        <div>
          <span className="measurement__title">Measurement Check</span>
          {run && <span className="measurement__run">{run.id.slice(0, 6)}</span>}
        </div>
        <div className="measurement__actions">
          <button
            type="button"
            className="measurement__button"
            onClick={() => generateSynthetic(run ?? null)}
            disabled={!run || run.status !== 'succeeded'}
          >
            Synthesise
          </button>
          <label className="measurement__button measurement__button--upload">
            Upload
            <input
              ref={fileInputRef}
              type="file"
              accept=".mdat,.dat,.txt,.json"
              onChange={handleFileChange}
            />
          </label>
          <button
            type="button"
            className="measurement__button measurement__button--primary"
            onClick={() => {
              if (run) {
                void compareWithRun(run)
              }
            }}
            disabled={!canCompare || loading}
          >
            {loading ? 'Comparing…' : 'Compare'}
          </button>
        </div>
      </header>
      {body}
    </aside>
  )
}
