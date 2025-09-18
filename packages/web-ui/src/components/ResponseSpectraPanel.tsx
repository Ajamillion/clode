import { useMemo } from 'react'
import { useOptimization } from '@stores/optimization.store'
import type { OptimizationRun } from '@types/index'

const CHART_WIDTH = 320
const CHART_HEIGHT = 164
const CHART_PADDING = 28

type ChartData = {
  id: string
  label: string
  unit: string
  color: string
  path: string
  minValue: number
  maxValue: number
  freqMin: number
  freqMax: number
}

type ChartConfig = {
  id: string
  label: string
  unit: string
  color: string
}

function buildChart(
  frequency: number[] | undefined,
  values: number[] | undefined,
  config: ChartConfig
): ChartData | null {
  if (!frequency || !values) return null
  const length = Math.min(frequency.length, values.length)
  if (length < 2) return null

  const points: { freq: number; value: number }[] = []
  for (let i = 0; i < length; i += 1) {
    const freq = Number(frequency[i])
    const value = Number(values[i])
    if (!Number.isFinite(freq) || freq <= 0 || !Number.isFinite(value)) {
      continue
    }
    points.push({ freq, value })
  }

  if (points.length < 2) return null

  points.sort((a, b) => a.freq - b.freq)

  const freqMin = points[0]!.freq
  const freqMax = points[points.length - 1]!.freq
  const logMin = Math.log10(freqMin)
  const logMax = Math.log10(freqMax)

  let minValue = points[0]!.value
  let maxValue = points[0]!.value
  for (const point of points) {
    if (point.value < minValue) minValue = point.value
    if (point.value > maxValue) maxValue = point.value
  }

  if (maxValue === minValue) {
    const delta = Math.abs(maxValue) * 0.05 || 1
    minValue -= delta
    maxValue += delta
  }

  const innerWidth = CHART_WIDTH - CHART_PADDING * 2
  const innerHeight = CHART_HEIGHT - CHART_PADDING * 2
  const range = maxValue - minValue || 1

  const path = points
    .map((point, index) => {
      let x: number
      if (logMax === logMin) {
        const denominator = Math.max(points.length - 1, 1)
        x = CHART_PADDING + (index / denominator) * innerWidth
      } else {
        const norm = (Math.log10(point.freq) - logMin) / (logMax - logMin)
        x = CHART_PADDING + norm * innerWidth
      }
      const normY = (point.value - minValue) / range
      const y = CHART_HEIGHT - CHART_PADDING - normY * innerHeight
      const command = index === 0 ? 'M' : 'L'
      return `${command}${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')

  return {
    id: config.id,
    label: config.label,
    unit: config.unit,
    color: config.color,
    path,
    minValue,
    maxValue,
    freqMin,
    freqMax
  }
}

function truncateId(id: string) {
  return id.length <= 8 ? id : `${id.slice(0, 4)}…${id.slice(-4)}`
}

function formatRange(min: number, max: number, unit: string) {
  const fmt = (value: number) => {
    const abs = Math.abs(value)
    if (abs >= 100) return value.toFixed(0)
    if (abs >= 10) return value.toFixed(1)
    return value.toFixed(2)
  }
  return `${fmt(min)} – ${fmt(max)} ${unit}`
}

function formatHz(value: number) {
  if (!Number.isFinite(value)) return '—'
  if (value >= 100) return `${value.toFixed(0)} Hz`
  if (value >= 10) return `${value.toFixed(1)} Hz`
  return `${value.toFixed(2)} Hz`
}

function formatRelative(tsSeconds: number | null | undefined) {
  if (!tsSeconds) return '—'
  const timestamp = tsSeconds * 1000
  const delta = Date.now() - timestamp
  if (delta < 0) return 'just now'
  const minutes = Math.floor(delta / 60000)
  if (minutes <= 1) return 'moments ago'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function buildSummary(run: OptimizationRun | null) {
  const metrics = run?.result?.metrics
  const summary = run?.result?.summary
  const entries: { label: string; value: string }[] = []

  const metricValue = (key: string) => {
    const value = metrics?.[key]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  }

  const summaryValue = (key: string) => {
    const value = summary?.[key]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  }

  const add = (label: string, value: number | null, formatter: (input: number) => string) => {
    if (value == null) return
    entries.push({ label, value: formatter(value) })
  }

  add('Achieved SPL', metricValue('achieved_spl_db'), (value) => `${value.toFixed(1)} dB`)
  add('Target SPL', metricValue('target_spl_db'), (value) => `${value.toFixed(1)} dB`)
  add('Safe drive', metricValue('safe_drive_voltage_v') ?? summaryValue('safe_drive_voltage_v'), (value) => `${value.toFixed(2)} V`)
  add('Enclosure volume', metricValue('volume_l'), (value) => `${value.toFixed(1)} L`)
  add('Alignment Fc', summaryValue('fc_hz'), (value) => `${value.toFixed(1)} Hz`)
  add('Alignment Fb', summaryValue('fb_hz'), (value) => `${value.toFixed(1)} Hz`)
  add('Excursion headroom', summaryValue('excursion_headroom_db'), (value) => `${value.toFixed(1)} dB`)
  add('Max port velocity', summaryValue('max_port_velocity_ms'), (value) => `${value.toFixed(1)} m/s`)
  add('Max displacement', summaryValue('max_cone_displacement_m'), (value) => `${(value * 1000).toFixed(2)} mm`)

  return entries.slice(0, 6)
}

export function ResponseSpectraPanel() {
  const selectedRunId = useOptimization((state) => state.selectedRunId)
  const recentRuns = useOptimization((state) => state.recentRuns)
  const lastRun = useOptimization((state) => state.lastRun)

  const selectedRun = useMemo(() => {
    if (selectedRunId) {
      const found = recentRuns.find((run) => run.id === selectedRunId)
      if (found) return found
      if (lastRun && lastRun.id === selectedRunId) return lastRun
    }
    return lastRun ?? recentRuns[0] ?? null
  }, [selectedRunId, recentRuns, lastRun])

  const response = selectedRun?.result?.response
  const frequencies = response?.frequency_hz
  const spl = response?.spl_db
  const impReal = response?.impedance_real
  const impImag = response?.impedance_imag
  const displacement = response?.cone_displacement_m
  const portVelocity = response?.port_velocity_ms
  const coneVelocity = response?.cone_velocity_ms

  const impedanceMagnitude = useMemo(() => {
    if (!impReal || !impImag) return undefined
    const length = Math.min(impReal.length, impImag.length)
    const values: number[] = []
    for (let i = 0; i < length; i += 1) {
      const real = impReal[i]
      const imag = impImag[i]
      if (Number.isFinite(real) && Number.isFinite(imag)) {
        values.push(Math.hypot(real, imag))
      }
    }
    return values.length ? values : undefined
  }, [impReal, impImag])

  const charts = useMemo(() => {
    const defs: ChartData[] = []
    const splChart = buildChart(frequencies, spl, {
      id: 'spl',
      label: 'SPL',
      unit: 'dB',
      color: '#f97316'
    })
    if (splChart) defs.push(splChart)

    const impedanceChart = buildChart(frequencies, impedanceMagnitude, {
      id: 'impedance',
      label: 'Impedance magnitude',
      unit: 'Ω',
      color: '#38bdf8'
    })
    if (impedanceChart) defs.push(impedanceChart)

    const portChart = buildChart(frequencies, portVelocity, {
      id: 'port-velocity',
      label: 'Port velocity',
      unit: 'm/s',
      color: '#60a5fa'
    })
    if (portChart) {
      defs.push(portChart)
    } else {
      const displacementChart = buildChart(
        frequencies,
        displacement?.map((value) => value * 1000),
        {
          id: 'displacement',
          label: 'Cone displacement',
          unit: 'mm',
          color: '#a855f7'
        }
      )
      if (displacementChart) {
        defs.push(displacementChart)
      } else {
        const velocityChart = buildChart(frequencies, coneVelocity, {
          id: 'cone-velocity',
          label: 'Cone velocity',
          unit: 'm/s',
          color: '#22d3ee'
        })
        if (velocityChart) defs.push(velocityChart)
      }
    }

    return defs
  }, [frequencies, spl, impedanceMagnitude, portVelocity, displacement, coneVelocity])

  const summaryEntries = useMemo(() => buildSummary(selectedRun), [selectedRun])
  const updatedAt = selectedRun ? formatRelative(selectedRun.updated_at) : '—'
  const alignment = selectedRun?.result?.alignment
  const status = selectedRun?.status

  return (
    <aside className="spectra" aria-live="polite">
      <header className="spectra__header">
        <div>
          <span className="spectra__title">Frequency response</span>
          {selectedRun && <span className="spectra__run-id">#{truncateId(selectedRun.id)}</span>}
        </div>
        {alignment && <span className="spectra__tag">{alignment}</span>}
      </header>

      <div className="spectra__meta">
        <span className="spectra__status">{status ?? 'no run selected'}</span>
        <span className="spectra__updated">updated {updatedAt}</span>
      </div>

      <div className="spectra__charts">
        {charts.length === 0 ? (
          <div className="spectra__empty">
            Select a completed optimisation run to view SPL and impedance traces.
          </div>
        ) : (
          charts.map((chart) => (
            <div key={chart.id} className="spectra__chart">
              <div className="spectra__chart-header">
                <span>{chart.label}</span>
                <span className="spectra__chart-range">
                  {formatRange(chart.minValue, chart.maxValue, chart.unit)}
                </span>
              </div>
              <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} role="img" aria-label={chart.label}>
                <defs>
                  <linearGradient id={`grad-${chart.id}`} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor={chart.color} stopOpacity={0.45} />
                    <stop offset="100%" stopColor={chart.color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <path d={`${chart.path} L${CHART_WIDTH - CHART_PADDING} ${CHART_HEIGHT - CHART_PADDING} L${CHART_PADDING} ${CHART_HEIGHT - CHART_PADDING} Z`} fill={`url(#grad-${chart.id})`} opacity={0.35} />
                <path d={chart.path} stroke={chart.color} strokeWidth={2.2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <div className="spectra__axis">
                <span>{formatHz(chart.freqMin)}</span>
                <span>Frequency</span>
                <span>{formatHz(chart.freqMax)}</span>
              </div>
            </div>
          ))
        )}
      </div>

      {summaryEntries.length > 0 && (
        <dl className="spectra__summary">
          {summaryEntries.map((entry) => (
            <div key={entry.label} className="spectra__summary-item">
              <dt>{entry.label}</dt>
              <dd>{entry.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </aside>
  )
}
