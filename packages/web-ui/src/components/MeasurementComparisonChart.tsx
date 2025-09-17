import { useMemo } from 'react'
import type { MeasurementComparison, MeasurementTrace } from '@types/index'

const CHART_WIDTH = 320
const CHART_HEIGHT = 192
const CHART_PADDING = 32

type SeriesKey = 'measurement' | 'baseline' | 'calibrated'

type SeriesConfig = {
  id: SeriesKey
  label: string
  color: string
  strokeWidth: number
  dash?: string
}

const SERIES_CONFIG: Record<SeriesKey, SeriesConfig> = {
  measurement: {
    id: 'measurement',
    label: 'Measurement',
    color: '#f97316',
    strokeWidth: 1.8,
  },
  baseline: {
    id: 'baseline',
    label: 'Solver prediction',
    color: '#38bdf8',
    strokeWidth: 1.4,
  },
  calibrated: {
    id: 'calibrated',
    label: 'Calibrated rerun',
    color: '#22c55e',
    strokeWidth: 1.4,
    dash: '5 3',
  },
}

type SeriesPoint = {
  freq: number
  value: number
}

type RawSeries = SeriesConfig & {
  points: SeriesPoint[]
}

type ChartSeries = SeriesConfig & {
  path: string
}

type ChartGeometry = {
  series: ChartSeries[]
  freqTicks: { value: number; x: number }[]
  valueTicks: { value: number; y: number }[]
  freqRange: { min: number; max: number }
  valueRange: { min: number; max: number }
}

function sanitisePoints(trace: MeasurementTrace | null | undefined): SeriesPoint[] | null {
  if (!trace?.frequency_hz?.length || !trace?.spl_db?.length) return null
  const length = Math.min(trace.frequency_hz.length, trace.spl_db.length)
  const points: SeriesPoint[] = []
  for (let i = 0; i < length; i += 1) {
    const freq = Number(trace.frequency_hz[i])
    const value = Number(trace.spl_db[i])
    if (!Number.isFinite(freq) || freq <= 0) continue
    if (!Number.isFinite(value)) continue
    points.push({ freq, value })
  }
  if (points.length < 2) return null
  points.sort((a, b) => a.freq - b.freq)
  return points
}

function createSeries(trace: MeasurementTrace | null | undefined, config: SeriesConfig): RawSeries | null {
  const points = sanitisePoints(trace)
  if (!points) return null
  return {
    ...config,
    points,
  }
}

function formatHz(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '—'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  if (value >= 100) return value.toFixed(0)
  if (value >= 10) return value.toFixed(1)
  return value.toFixed(2)
}

function formatHzRange(min: number, max: number) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return '—'
  return `${formatHz(min)} – ${formatHz(max)} Hz`
}

function formatDbRange(min: number, max: number) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return '—'
  return `${min.toFixed(1)} – ${max.toFixed(1)} dB`
}

function buildChartGeometry(series: RawSeries[]): ChartGeometry | null {
  if (!series.length) return null

  let freqMin = Number.POSITIVE_INFINITY
  let freqMax = Number.NEGATIVE_INFINITY
  let valueMin = Number.POSITIVE_INFINITY
  let valueMax = Number.NEGATIVE_INFINITY

  for (const entry of series) {
    for (const point of entry.points) {
      if (point.freq < freqMin) freqMin = point.freq
      if (point.freq > freqMax) freqMax = point.freq
      if (point.value < valueMin) valueMin = point.value
      if (point.value > valueMax) valueMax = point.value
    }
  }

  if (!Number.isFinite(freqMin) || !Number.isFinite(freqMax)) return null
  if (!Number.isFinite(valueMin) || !Number.isFinite(valueMax)) return null
  if (freqMin <= 0 || freqMax <= 0) return null

  const displayFreq = { min: freqMin, max: freqMax }
  const displayValue = { min: valueMin, max: valueMax }

  if (freqMax - freqMin < 1e-6) {
    freqMin *= 0.95
    freqMax *= 1.05
  }

  let scaledValueMin = valueMin
  let scaledValueMax = valueMax
  const pad = (scaledValueMax - scaledValueMin) * 0.08
  if (Number.isFinite(pad) && pad > 0) {
    scaledValueMin -= pad
    scaledValueMax += pad
  } else {
    const fallback = Math.max(1, Math.abs(scaledValueMax || scaledValueMin || 1) * 0.05)
    scaledValueMin -= fallback
    scaledValueMax += fallback
  }
  if (scaledValueMax <= scaledValueMin) {
    scaledValueMax = scaledValueMin + 1
  }

  const logMin = Math.log10(freqMin)
  const logMax = Math.log10(freqMax)
  const logRange = Math.max(logMax - logMin, 1e-6)

  const innerWidth = CHART_WIDTH - CHART_PADDING * 2
  const innerHeight = CHART_HEIGHT - CHART_PADDING * 2
  const valueRange = scaledValueMax - scaledValueMin || 1

  const chartSeries: ChartSeries[] = series.map((entry) => {
    const segments: string[] = []
    for (const [index, point] of entry.points.entries()) {
      const normX = logRange <= 1e-6 ? index / Math.max(entry.points.length - 1, 1) : (Math.log10(point.freq) - logMin) / logRange
      const normY = (point.value - scaledValueMin) / valueRange
      const x = CHART_PADDING + normX * innerWidth
      const y = CHART_HEIGHT - CHART_PADDING - normY * innerHeight
      segments.push(`${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`)
    }
    return {
      id: entry.id,
      label: entry.label,
      color: entry.color,
      strokeWidth: entry.strokeWidth,
      dash: entry.dash,
      path: segments.join(' '),
    }
  })

  const freqTicks: { value: number; x: number }[] = []
  for (let i = 0; i <= 4; i += 1) {
    const ratio = i / 4
    const value = Math.pow(10, logMin + ratio * (logMax - logMin))
    const normX = logRange <= 1e-6 ? ratio : (Math.log10(value) - logMin) / logRange
    const x = CHART_PADDING + normX * innerWidth
    freqTicks.push({ value, x })
  }

  const valueTicks: { value: number; y: number }[] = []
  for (let i = 0; i <= 4; i += 1) {
    const ratio = i / 4
    const value = scaledValueMin + ratio * valueRange
    const y = CHART_HEIGHT - CHART_PADDING - ratio * innerHeight
    valueTicks.push({ value, y })
  }

  return {
    series: chartSeries,
    freqTicks,
    valueTicks,
    freqRange: displayFreq,
    valueRange: displayValue,
  }
}

type MeasurementComparisonChartProps = {
  measurement: MeasurementTrace | null
  comparison: MeasurementComparison | null
}

export function MeasurementComparisonChart({ measurement, comparison }: MeasurementComparisonChartProps) {
  const chart = useMemo(() => {
    const series: RawSeries[] = []
    const measurementSeries = createSeries(measurement, SERIES_CONFIG.measurement)
    if (measurementSeries) series.push(measurementSeries)
    const baselineSeries = createSeries(comparison?.prediction ?? null, SERIES_CONFIG.baseline)
    if (baselineSeries) series.push(baselineSeries)
    const calibratedSeries = createSeries(comparison?.calibrated?.prediction ?? null, SERIES_CONFIG.calibrated)
    if (calibratedSeries) series.push(calibratedSeries)
    return buildChartGeometry(series)
  }, [measurement, comparison])

  if (!chart) return null

  return (
    <div className="measurement__chart">
      <div className="measurement__chart-head">
        <span className="measurement__chart-title">Frequency response overlay</span>
        <span className="measurement__chart-subtitle">SPL (dB)</span>
      </div>
      <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="measurement__chart-plot" role="img" aria-label="Measurement versus solver frequency response">
        <defs>
          <linearGradient id="measurementChartBg" x1="0%" x2="0%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(15, 23, 42, 0.65)" />
            <stop offset="100%" stopColor="rgba(15, 23, 42, 0.35)" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width={CHART_WIDTH} height={CHART_HEIGHT} fill="url(#measurementChartBg)" rx="18" />
        <line
          x1={CHART_PADDING}
          y1={CHART_HEIGHT - CHART_PADDING}
          x2={CHART_WIDTH - CHART_PADDING}
          y2={CHART_HEIGHT - CHART_PADDING}
          className="measurement__chart-axis"
        />
        <line
          x1={CHART_PADDING}
          y1={CHART_PADDING}
          x2={CHART_PADDING}
          y2={CHART_HEIGHT - CHART_PADDING}
          className="measurement__chart-axis"
        />
        {chart.freqTicks.map((tick, index) => (
          <g key={`freq-${index}`}>
            <line
              x1={tick.x}
              y1={CHART_PADDING}
              x2={tick.x}
              y2={CHART_HEIGHT - CHART_PADDING}
              className="measurement__chart-grid"
            />
            <text x={tick.x} y={CHART_HEIGHT - CHART_PADDING + 12} className="measurement__chart-tick" textAnchor="middle">
              {formatHz(tick.value)}
            </text>
          </g>
        ))}
        {chart.valueTicks.map((tick, index) => (
          <g key={`value-${index}`}>
            <line
              x1={CHART_PADDING}
              y1={tick.y}
              x2={CHART_WIDTH - CHART_PADDING}
              y2={tick.y}
              className="measurement__chart-grid"
            />
            <text x={CHART_PADDING - 8} y={tick.y + 2} className="measurement__chart-tick" textAnchor="end">
              {tick.value.toFixed(0)}
            </text>
          </g>
        ))}
        {chart.series.map((entry) => (
          <path
            key={entry.id}
            d={entry.path}
            fill="none"
            stroke={entry.color}
            strokeWidth={entry.strokeWidth}
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeDasharray={entry.dash}
          />
        ))}
      </svg>
      <ul className="measurement__chart-legend">
        {chart.series.map((entry) => (
          <li key={entry.id}>
            <span className="measurement__chart-swatch" style={{ background: entry.color }} />
            {entry.label}
          </li>
        ))}
      </ul>
      <div className="measurement__chart-range">
        <span>Frequency: {formatHzRange(chart.freqRange.min, chart.freqRange.max)}</span>
        <span>SPL: {formatDbRange(chart.valueRange.min, chart.valueRange.max)}</span>
      </div>
    </div>
  )
}
