import { useMemo, useRef, type ChangeEventHandler } from 'react'
import { MeasurementComparisonChart } from '@components/MeasurementComparisonChart'
import { useMeasurement } from '@stores/measurement.store'
import { useOptimization } from '@stores/optimization.store'
import type {
  MeasurementCalibrationParameter,
  MeasurementTrace,
  OptimizationRun,
} from '@types/index'

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

function formatPercent(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  const percent = value * 100
  const sign = percent > 0 ? '+' : percent < 0 ? '−' : ''
  const abs = Math.abs(percent)
  const precision = abs < 10 ? 1 : 0
  return `${sign}${abs.toFixed(precision)}%`
}

function formatWeight(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  const clamped = Math.min(Math.max(value, 0), 1)
  return `${Math.round(clamped * 100)}%`
}

function formatScalar(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

function formatScalePercent(scale: number | null | undefined) {
  if (scale == null || !Number.isFinite(scale)) return '—'
  return formatPercent(scale - 1)
}

function formatScaleDb(scale: number | null | undefined) {
  if (scale == null || !Number.isFinite(scale) || scale <= 0) return '—'
  const db = 20 * Math.log10(scale)
  return formatDecibel(db)
}

function formatCalibrationLevel(parameter: MeasurementCalibrationParameter | null | undefined) {
  if (!parameter) return null
  const base = formatDecibel(parameter.mean)
  const weight = formatWeight(parameter.update_weight)
  const interval = parameter.credible_interval
  if (interval) {
    return `${base} (95%: ${formatDecibel(interval.lower)} → ${formatDecibel(interval.upper)}, weight ${weight})`
  }
  return `${base} (weight ${weight})`
}

function formatCalibrationScale(parameter: MeasurementCalibrationParameter | null | undefined) {
  if (!parameter) return null
  const base = formatPercent(parameter.mean - 1)
  const weight = formatWeight(parameter.update_weight)
  const interval = parameter.credible_interval
  if (interval) {
    return `${base} (95%: ${formatPercent(interval.lower - 1)} → ${formatPercent(interval.upper - 1)}, weight ${weight})`
  }
  return `${base} (weight ${weight})`
}

function formatVoltage(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(2)} V`
}

function formatFrequencyDelta(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  const abs = Math.abs(value)
  if (abs >= 1000) return `${sign}${(abs / 1000).toFixed(2)} kHz`
  return `${sign}${abs.toFixed(2)} Hz`
}

function formatLength(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  if (value >= 1) return `${value.toFixed(2)} m`
  if (value >= 0.1) return `${(value * 100).toFixed(1)} cm`
  return `${(value * 1000).toFixed(0)} mm`
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
  const minFrequencyHz = useMeasurement((state) => state.minFrequencyHz)
  const maxFrequencyHz = useMeasurement((state) => state.maxFrequencyHz)
  const setFrequencyBand = useMeasurement((state) => state.setFrequencyBand)

  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const measurementSummary = useMemo(() => summariseMeasurement(preview), [preview])

  const comparisonBand = useMemo(() => {
    const band = comparison?.frequency_band
    if (band) {
      return {
        min: band.min_hz ?? null,
        max: band.max_hz ?? null,
      }
    }
    return {
      min: minFrequencyHz ?? measurementSummary?.minFreq ?? null,
      max: maxFrequencyHz ?? measurementSummary?.maxFreq ?? null,
    }
  }, [
    comparison?.frequency_band?.min_hz,
    comparison?.frequency_band?.max_hz,
    minFrequencyHz,
    maxFrequencyHz,
    measurementSummary?.minFreq,
    measurementSummary?.maxFreq,
  ])

  const highlightEntries = useMemo(() => {
    const entries: { label: string; value: string }[] = []
    const band = comparison?.frequency_band
    if (band) {
      entries.push({
        label: 'Band',
        value: `${formatFrequency(band.min_hz ?? null)} → ${formatFrequency(band.max_hz ?? null)}`,
      })
    }
    const stats = comparison?.stats
    if (stats) {
      if (stats.spl_rmse_db != null) entries.push({ label: 'SPL RMSE', value: formatDecibel(stats.spl_rmse_db) })
      if (stats.spl_bias_db != null) entries.push({ label: 'SPL bias', value: formatDecibel(stats.spl_bias_db) })
      if (stats.max_spl_delta_db != null) entries.push({ label: 'Worst delta', value: formatDecibel(stats.max_spl_delta_db) })
      if (stats.phase_rmse_deg != null) entries.push({ label: 'Phase RMSE', value: `${stats.phase_rmse_deg.toFixed(2)}°` })
      if (stats.impedance_mag_rmse_ohm != null) entries.push({ label: 'Impedance RMSE', value: `${stats.impedance_mag_rmse_ohm.toFixed(2)} Ω` })
    }
    const summary = comparison?.summary
    if (summary) {
      if (summary.max_spl_db != null) entries.push({ label: 'Predicted SPL', value: formatDecibel(summary.max_spl_db) })
      if (summary.safe_drive_voltage_v != null) entries.push({ label: 'Safe drive', value: formatVoltage(summary.safe_drive_voltage_v) })
      if (summary.excursion_headroom_db != null) entries.push({ label: 'Excursion headroom', value: formatDecibel(summary.excursion_headroom_db) })
      if (summary.fb_hz != null) entries.push({ label: 'Fb', value: formatFrequency(summary.fb_hz) })
    }
    const diagnosis = comparison?.diagnosis
    if (diagnosis) {
      if (diagnosis.recommended_level_trim_db != null) {
        entries.push({ label: 'Level trim', value: formatDecibel(diagnosis.recommended_level_trim_db) })
      }
      if (diagnosis.tuning_shift_hz != null) {
        entries.push({ label: 'Tuning shift', value: formatFrequencyDelta(diagnosis.tuning_shift_hz) })
      }
      if (diagnosis.recommended_port_length_m != null) {
        const delta = diagnosis.recommended_port_length_scale != null ? diagnosis.recommended_port_length_scale - 1 : null
        entries.push({
          label: 'Port length',
          value: `${formatLength(diagnosis.recommended_port_length_m)} (${formatPercent(delta)})`,
        })
      }
      if (diagnosis.leakage_hint) {
        entries.push({
          label: 'Leakage',
          value: diagnosis.leakage_hint === 'lower_q' ? 'Reduce leakage Q' : 'Increase leakage Q',
        })
      }
    }
    const calibration = comparison?.calibration
    if (calibration) {
      const level = formatCalibrationLevel(calibration.level_trim_db ?? null)
      if (level) {
        entries.push({ label: 'Posterior level trim', value: level })
      }
      const port = formatCalibrationScale(calibration.port_length_scale ?? null)
      if (port) {
        entries.push({ label: 'Posterior port scale', value: port })
      }
      const leakage = formatCalibrationScale(calibration.leakage_q_scale ?? null)
      if (leakage) {
        entries.push({ label: 'Posterior leakage', value: leakage })
      }
    }
    const overrides = comparison?.calibration_overrides
    if (overrides) {
      const driveScale = overrides.drive_voltage_scale ?? null
      if (driveScale != null || overrides.drive_voltage_v != null) {
        entries.push({
          label: 'Recommended drive',
          value: `${formatVoltage(overrides.drive_voltage_v ?? null)} (${formatScalePercent(driveScale)}, ${formatScaleDb(driveScale)})`,
        })
      }
      if (overrides.port_length_m != null || overrides.port_length_scale != null) {
        entries.push({
          label: 'Recommended port length',
          value: `${formatLength(overrides.port_length_m ?? null)} (${formatScalePercent(overrides.port_length_scale ?? null)})`,
        })
      }
      if (overrides.leakage_q != null || overrides.leakage_q_scale != null) {
        entries.push({
          label: 'Recommended leakage Q',
          value: `${formatScalar(overrides.leakage_q ?? null, 2)} (${formatScalePercent(overrides.leakage_q_scale ?? null)})`,
        })
      }
    }
    const calibrated = comparison?.calibrated
    if (calibrated) {
      const inputs = calibrated.inputs
      if (inputs) {
        if (inputs.drive_voltage_v != null) {
          entries.push({ label: 'Rerun drive', value: formatVoltage(inputs.drive_voltage_v) })
        }
        if (inputs.port_length_m != null) {
          entries.push({ label: 'Rerun port length', value: formatLength(inputs.port_length_m) })
        }
        if (inputs.leakage_q != null) {
          entries.push({ label: 'Rerun leakage Q', value: formatScalar(inputs.leakage_q, 2) })
        }
      }
      const calStats = calibrated.stats
      if (calStats) {
        if (calStats.spl_rmse_db != null) {
          entries.push({ label: 'Rerun SPL RMSE', value: formatDecibel(calStats.spl_rmse_db) })
        }
        if (calStats.spl_bias_db != null) {
          entries.push({ label: 'Rerun SPL bias', value: formatDecibel(calStats.spl_bias_db) })
        }
        if (calStats.max_spl_delta_db != null) {
          entries.push({ label: 'Rerun worst delta', value: formatDecibel(calStats.max_spl_delta_db) })
        }
      }
      const calSummary = calibrated.summary
      if (calSummary) {
        if (calSummary.safe_drive_voltage_v != null) {
          entries.push({ label: 'Rerun safe drive', value: formatVoltage(calSummary.safe_drive_voltage_v) })
        }
        if (calSummary.fb_hz != null) {
          entries.push({ label: 'Rerun Fb', value: formatFrequency(calSummary.fb_hz) })
        }
      }
    }
    return entries
  }, [comparison])

  const diagnosisNotes = useMemo(() => {
    const notes = comparison?.diagnosis?.notes
    if (!notes) return []
    return notes.map((note) => String(note)).filter((note) => note.length > 0)
  }, [comparison])

  const calibrationNotes = useMemo(() => {
    const notes = comparison?.calibration?.notes
    if (!notes) return []
    return notes.map((note) => String(note)).filter((note) => note.length > 0)
  }, [comparison])

  const calibratedNotes = useMemo(() => {
    const notes = comparison?.calibrated?.diagnosis?.notes
    if (!notes) return []
    return notes.map((note) => String(note)).filter((note) => note.length > 0)
  }, [comparison])

  const insightNotes = useMemo(() => {
    if (!diagnosisNotes.length && !calibrationNotes.length && !calibratedNotes.length) return []
    return [...diagnosisNotes, ...calibrationNotes, ...calibratedNotes]
  }, [diagnosisNotes, calibrationNotes, calibratedNotes])

  const canCompare = !!preview && run?.status === 'succeeded'

  const handleFileChange: ChangeEventHandler<HTMLInputElement> = (event) => {
    const file = event.currentTarget.files?.[0]
    if (file) {
      void previewFromFile(file)
    }
    event.currentTarget.value = ''
  }

  const handleBandChange = (type: 'min' | 'max'): ChangeEventHandler<HTMLInputElement> => (event) => {
    const raw = event.currentTarget.value ?? ''
    const trimmed = raw.trim()
    const parsed = trimmed.length > 0 ? Number(trimmed) : null
    const sanitized = parsed != null && Number.isFinite(parsed) ? parsed : null
    if (type === 'min') {
      setFrequencyBand(sanitized, maxFrequencyHz)
    } else {
      setFrequencyBand(minFrequencyHz, sanitized)
    }
  }

  const applyPreviewBand = () => {
    if (!measurementSummary) return
    setFrequencyBand(measurementSummary.minFreq ?? null, measurementSummary.maxFreq ?? null)
  }

  const clearBand = () => {
    setFrequencyBand(null, null)
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
            <>
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
              <div className="measurement__band">
                <div className="measurement__band-info">
                  <span>Comparison band</span>
                  <strong>
                    {formatFrequency(comparisonBand.min)}
                    <span className="measurement__band-arrow"> → </span>
                    {formatFrequency(comparisonBand.max)}
                  </strong>
                </div>
                <div className="measurement__band-controls">
                  <input
                    type="number"
                    min={0}
                    step="1"
                    placeholder="Min Hz"
                    value={minFrequencyHz ?? ''}
                    onChange={handleBandChange('min')}
                  />
                  <span className="measurement__band-sep">→</span>
                  <input
                    type="number"
                    min={0}
                    step="1"
                    placeholder="Max Hz"
                    value={maxFrequencyHz ?? ''}
                    onChange={handleBandChange('max')}
                  />
                  <button type="button" onClick={applyPreviewBand} disabled={!measurementSummary}>
                    Use preview span
                  </button>
                  <button type="button" onClick={clearBand} className="measurement__band-reset">
                    Reset
                  </button>
                </div>
                <p className="measurement__band-hint">Leave fields blank to compare across the full measurement span.</p>
              </div>
            </>
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
              {(highlightEntries.length > 0 || insightNotes.length > 0) && (
                <div className="measurement__highlights">
                  {highlightEntries.map((entry) => (
                    <div key={entry.label}>
                      <dt>{entry.label}</dt>
                      <dd>{entry.value}</dd>
                    </div>
                  ))}
                  {insightNotes.length > 0 && (
                    <div className="measurement__notes">
                      <dt>Insights</dt>
                      <dd>
                        <ul>
                          {insightNotes.map((note, idx) => (
                            <li key={`${idx}-${note}`}>{note}</li>
                          ))}
                        </ul>
                      </dd>
                    </div>
                  )}
                </div>
              )}
              <MeasurementComparisonChart measurement={preview} comparison={comparison} />
              <button type="button" className="measurement__clear" onClick={() => clearComparison()}>
                Clear comparison
              </button>
            </div>
          ) : (
            <p className="measurement__empty">Run a comparison to surface SPL, phase, impedance, and THD overlays alongside the solver deltas.</p>
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
