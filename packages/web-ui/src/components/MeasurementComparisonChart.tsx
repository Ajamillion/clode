import { useEffect, useMemo, useState } from 'react'
import type { MeasurementComparison, MeasurementDelta, MeasurementTrace } from '@types/index'

const CHART_WIDTH = 320
const CHART_HEIGHT = 192
const CHART_PADDING = 32

const METRIC_ORDER = ['spl', 'phase', 'impedance', 'thd'] as const

type ComparisonMetric = (typeof METRIC_ORDER)[number]
type ChartMode = 'overlay' | 'delta'

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
  zeroY: number | null
}

type MetricDefinition = {
  key: ComparisonMetric
  label: string
  overlayTitle: string
  deltaTitle: string
  overlaySubtitle: string
  deltaSubtitle: string
  overlayRangeLabel: string
  deltaRangeLabel: string
  measurementAccessor: (
    trace: MeasurementTrace | null | undefined,
  ) => number[] | null
  deltaAccessor: (delta: MeasurementDelta | null | undefined) => number[] | null
  formatTick: (value: number, mode: ChartMode) => string
  formatRange: (min: number, max: number, mode: ChartMode) => string
}

const METRIC_CONFIG: Record<ComparisonMetric, MetricDefinition> = {
  spl: {
    key: 'spl',
    label: 'SPL',
    overlayTitle: 'Frequency response overlay',
    deltaTitle: 'SPL delta versus solver',
    overlaySubtitle: 'SPL (dB)',
    deltaSubtitle: 'ΔSPL (dB)',
    overlayRangeLabel: 'SPL',
    deltaRangeLabel: 'ΔSPL',
    measurementAccessor: getSplSeries,
    deltaAccessor: getSplDelta,
    formatTick: formatDbTick,
    formatRange: formatDbRange,
  },
  phase: {
    key: 'phase',
    label: 'Phase',
    overlayTitle: 'Phase overlay',
    deltaTitle: 'Phase delta versus solver',
    overlaySubtitle: 'Phase (°)',
    deltaSubtitle: 'ΔPhase (°)',
    overlayRangeLabel: 'Phase',
    deltaRangeLabel: 'ΔPhase',
    measurementAccessor: getPhaseSeries,
    deltaAccessor: getPhaseDelta,
    formatTick: formatPhaseTick,
    formatRange: formatPhaseRange,
  },
  impedance: {
    key: 'impedance',
    label: '|Z|',
    overlayTitle: 'Impedance overlay',
    deltaTitle: 'Impedance delta versus solver',
    overlaySubtitle: '|Z| (Ω)',
    deltaSubtitle: 'Δ|Z| (Ω)',
    overlayRangeLabel: '|Z|',
    deltaRangeLabel: 'Δ|Z|',
    measurementAccessor: getImpedanceSeries,
    deltaAccessor: getImpedanceDelta,
    formatTick: formatOhmTick,
    formatRange: formatOhmRange,
  },
  thd: {
    key: 'thd',
    label: 'THD',
    overlayTitle: 'THD overlay',
    deltaTitle: 'THD delta versus solver',
    overlaySubtitle: 'THD (%)',
    deltaSubtitle: 'ΔTHD (%)',
    overlayRangeLabel: 'THD',
    deltaRangeLabel: 'ΔTHD',
    measurementAccessor: getThdSeries,
    deltaAccessor: getThdDelta,
    formatTick: formatPercentTick,
    formatRange: formatPercentRange,
  },
}

function getSplSeries(trace: MeasurementTrace | null | undefined) {
  return trace?.spl_db ?? null
}

function getPhaseSeries(trace: MeasurementTrace | null | undefined) {
  return trace?.phase_deg ?? null
}

function getImpedanceSeries(trace: MeasurementTrace | null | undefined) {
  if (!trace?.impedance_real || !trace?.impedance_imag) return null
  const length = Math.min(
    trace.frequency_hz?.length ?? 0,
    trace.impedance_real.length,
    trace.impedance_imag.length,
  )
  if (length < 2) return null
  const values = new Array<number>(length)
  for (let i = 0; i < length; i += 1) {
    const real = Number(trace.impedance_real[i])
    const imag = Number(trace.impedance_imag[i])
    if (!Number.isFinite(real) || !Number.isFinite(imag)) {
      values[i] = Number.NaN
    } else {
      values[i] = Math.hypot(real, imag)
    }
  }
  return values
}

function getThdSeries(trace: MeasurementTrace | null | undefined) {
  return trace?.thd_percent ?? null
}

function getSplDelta(delta: MeasurementDelta | null | undefined) {
  return delta?.spl_delta_db ?? null
}

function getPhaseDelta(delta: MeasurementDelta | null | undefined) {
  return delta?.phase_delta_deg ?? null
}

function getImpedanceDelta(delta: MeasurementDelta | null | undefined) {
  return delta?.impedance_delta_ohm ?? null
}

function getThdDelta(delta: MeasurementDelta | null | undefined) {
  return delta?.thd_delta_percent ?? null
}

function formatDbTick(value: number) {
  const abs = Math.abs(value)
  const digits = abs >= 10 ? 0 : 1
  return `${value.toFixed(digits)} dB`
}

function formatDbRange(min: number, max: number) {
  return `${min.toFixed(1)} – ${max.toFixed(1)} dB`
}

function formatPhaseTick(value: number) {
  return `${value.toFixed(0)}°`
}

function formatPhaseRange(min: number, max: number) {
  return `${min.toFixed(0)} – ${max.toFixed(0)} °`
}

function formatOhmValue(value: number) {
  const abs = Math.abs(value)
  if (abs >= 50) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(1)
  if (abs >= 1) return value.toFixed(2)
  return value.toFixed(3)
}

function formatOhmTick(value: number) {
  return `${formatOhmValue(value)} Ω`
}

function formatOhmRange(min: number, max: number) {
  return `${formatOhmValue(min)} – ${formatOhmValue(max)} Ω`
}

function formatPercentValue(value: number) {
  const abs = Math.abs(value)
  if (abs >= 10) return value.toFixed(0)
  if (abs >= 1) return value.toFixed(1)
  return value.toFixed(2)
}

function formatPercentTick(value: number) {
  return `${formatPercentValue(value)}%`
}

function formatPercentRange(min: number, max: number) {
  return `${formatPercentValue(min)} – ${formatPercentValue(max)} %`
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

function sanitisePoints(
  freq: number[] | undefined,
  values: number[] | null | undefined,
): SeriesPoint[] | null {
  if (!freq || !freq.length || !values) return null
  const limit = Math.min(freq.length, values.length)
  if (limit < 2) return null
  const points: SeriesPoint[] = []
  for (let i = 0; i < limit; i += 1) {
    const x = Number(freq[i])
    const y = Number(values[i])
    if (!Number.isFinite(x) || x <= 0) continue
    if (!Number.isFinite(y)) continue
    points.push({ freq: x, value: y })
  }
  if (points.length < 2) return null
  points.sort((a, b) => a.freq - b.freq)
  return points
}

function createOverlaySeries(
  trace: MeasurementTrace | null | undefined,
  accessor: (trace: MeasurementTrace | null | undefined) => number[] | null,
  config: SeriesConfig,
  label?: string,
): RawSeries | null {
  if (!trace?.frequency_hz?.length) return null
  const points = sanitisePoints(trace.frequency_hz, accessor(trace))
  if (!points) return null
  return {
    ...config,
    label: label ?? config.label,
    points,
  }
}

function createDeltaSeries(
  delta: MeasurementDelta | null | undefined,
  accessor: (delta: MeasurementDelta | null | undefined) => number[] | null,
  config: SeriesConfig,
  label?: string,
): RawSeries | null {
  if (!delta?.frequency_hz?.length) return null
  const points = sanitisePoints(delta.frequency_hz, accessor(delta))
  if (!points) return null
  return {
    ...config,
    label: label ?? config.label,
    points,
  }
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
      const normX =
        logRange <= 1e-6
          ? index / Math.max(entry.points.length - 1, 1)
          : (Math.log10(point.freq) - logMin) / logRange
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
    const normX =
      logRange <= 1e-6 ? ratio : (Math.log10(value) - logMin) / logRange
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

  let zeroY: number | null = null
  if (scaledValueMin < 0 && scaledValueMax > 0) {
    const zeroRatio = (0 - scaledValueMin) / valueRange
    zeroY = CHART_HEIGHT - CHART_PADDING - zeroRatio * innerHeight
  }

  return {
    series: chartSeries,
    freqTicks,
    valueTicks,
    freqRange: displayFreq,
    valueRange: displayValue,
    zeroY,
  }
}

function hasTraceSeries(
  trace: MeasurementTrace | null | undefined,
  accessor: (trace: MeasurementTrace | null | undefined) => number[] | null,
) {
  if (!trace?.frequency_hz?.length) return false
  return sanitisePoints(trace.frequency_hz, accessor(trace)) !== null
}

function hasDeltaSeries(
  delta: MeasurementDelta | null | undefined,
  accessor: (delta: MeasurementDelta | null | undefined) => number[] | null,
) {
  if (!delta?.frequency_hz?.length) return false
  return sanitisePoints(delta.frequency_hz, accessor(delta)) !== null
}

type MeasurementComparisonChartProps = {
  measurement: MeasurementTrace | null
  comparison: MeasurementComparison | null
}

export function MeasurementComparisonChart({ measurement, comparison }: MeasurementComparisonChartProps) {
  const [selectedMetric, setSelectedMetric] = useState<ComparisonMetric>('spl')
  const [mode, setMode] = useState<ChartMode>('overlay')

  const overlayAvailability = useMemo(() => {
    const availability: Record<ComparisonMetric, boolean> = {
      spl: false,
      phase: false,
      impedance: false,
      thd: false,
    }
    for (const metric of METRIC_ORDER) {
      const config = METRIC_CONFIG[metric]
      availability[metric] =
        hasTraceSeries(measurement, config.measurementAccessor) ||
        hasTraceSeries(comparison?.prediction ?? null, config.measurementAccessor) ||
        hasTraceSeries(comparison?.calibrated?.prediction ?? null, config.measurementAccessor)
    }
    return availability
  }, [measurement, comparison])

  const deltaAvailability = useMemo(() => {
    const availability: Record<ComparisonMetric, boolean> = {
      spl: false,
      phase: false,
      impedance: false,
      thd: false,
    }
    for (const metric of METRIC_ORDER) {
      const config = METRIC_CONFIG[metric]
      availability[metric] =
        hasDeltaSeries(comparison?.delta ?? null, config.deltaAccessor) ||
        hasDeltaSeries(comparison?.calibrated?.delta ?? null, config.deltaAccessor)
    }
    return availability
  }, [comparison])

  useEffect(() => {
    const available =
      overlayAvailability[selectedMetric] || deltaAvailability[selectedMetric]
    if (!available) {
      const fallback = METRIC_ORDER.find(
        (metric) => overlayAvailability[metric] || deltaAvailability[metric],
      )
      if (fallback && fallback !== selectedMetric) {
        setSelectedMetric(fallback)
      }
    }
  }, [selectedMetric, overlayAvailability, deltaAvailability])

  useEffect(() => {
    const overlayAvailable = overlayAvailability[selectedMetric]
    const deltaAvailable = deltaAvailability[selectedMetric]
    if (mode === 'overlay' && !overlayAvailable && deltaAvailable) {
      setMode('delta')
    } else if (mode === 'delta' && !deltaAvailable && overlayAvailable) {
      setMode('overlay')
    }
  }, [mode, selectedMetric, overlayAvailability, deltaAvailability])

  const config = METRIC_CONFIG[selectedMetric]

  const chart = useMemo(() => {
    if (!comparison && !measurement) return null
    if (mode === 'overlay') {
      const series: RawSeries[] = []
      const measurementSeries = createOverlaySeries(
        measurement,
        config.measurementAccessor,
        SERIES_CONFIG.measurement,
      )
      if (measurementSeries) series.push(measurementSeries)
      const baselineSeries = createOverlaySeries(
        comparison?.prediction ?? null,
        config.measurementAccessor,
        { ...SERIES_CONFIG.baseline },
      )
      if (baselineSeries) series.push(baselineSeries)
      const calibratedSeries = createOverlaySeries(
        comparison?.calibrated?.prediction ?? null,
        config.measurementAccessor,
        { ...SERIES_CONFIG.calibrated },
      )
      if (calibratedSeries) series.push(calibratedSeries)
      return buildChartGeometry(series)
    }

    const series: RawSeries[] = []
    const baselineDelta = createDeltaSeries(
      comparison?.delta ?? null,
      config.deltaAccessor,
      { ...SERIES_CONFIG.baseline, label: 'Baseline delta' },
    )
    if (baselineDelta) series.push(baselineDelta)
    const calibratedDelta = createDeltaSeries(
      comparison?.calibrated?.delta ?? null,
      config.deltaAccessor,
      { ...SERIES_CONFIG.calibrated, label: 'Calibrated delta' },
    )
    if (calibratedDelta) series.push(calibratedDelta)
    return buildChartGeometry(series)
  }, [comparison, measurement, config, mode])

  const activeTitle = mode === 'overlay' ? config.overlayTitle : config.deltaTitle
  const activeSubtitle = mode === 'overlay' ? config.overlaySubtitle : config.deltaSubtitle
  const rangeLabel = mode === 'overlay' ? config.overlayRangeLabel : config.deltaRangeLabel
  const emptyMessage =
    mode === 'overlay'
      ? `No ${config.label} overlay data available for this comparison.`
      : `No ${config.label} delta data available for this comparison.`

  const overlayEnabled = overlayAvailability[selectedMetric]
  const deltaEnabled = deltaAvailability[selectedMetric]

  return (
    <div className="measurement__chart">
      <div className="measurement__chart-controls">
        <div className="measurement__chart-tabs" role="tablist" aria-label="Measurement metric">
          {METRIC_ORDER.map((metric) => {
            const metricConfig = METRIC_CONFIG[metric]
            const isActive = selectedMetric === metric
            const enabled = overlayAvailability[metric] || deltaAvailability[metric]
            return (
              <button
                key={metric}
                type="button"
                className={`measurement__chart-toggle${isActive ? ' is-active' : ''}`}
                onClick={() => setSelectedMetric(metric)}
                disabled={!enabled}
                aria-pressed={isActive}
              >
                {metricConfig.label}
              </button>
            )
          })}
        </div>
        <div className="measurement__chart-modes" role="group" aria-label="Chart mode">
          <button
            type="button"
            className={`measurement__chart-toggle${mode === 'overlay' ? ' is-active' : ''}`}
            onClick={() => setMode('overlay')}
            disabled={!overlayEnabled}
            aria-pressed={mode === 'overlay'}
          >
            Overlay
          </button>
          <button
            type="button"
            className={`measurement__chart-toggle${mode === 'delta' ? ' is-active' : ''}`}
            onClick={() => setMode('delta')}
            disabled={!deltaEnabled}
            aria-pressed={mode === 'delta'}
          >
            Delta
          </button>
        </div>
      </div>
      <div className="measurement__chart-head">
        <span className="measurement__chart-title">{activeTitle}</span>
        <span className="measurement__chart-subtitle">{activeSubtitle}</span>
      </div>
      {chart ? (
        <>
          <svg
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            className="measurement__chart-plot"
            role="img"
            aria-label={`${activeTitle} chart`}
          >
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
                  {config.formatTick(tick.value, mode)}
                </text>
              </g>
            ))}
            {mode === 'delta' && chart.zeroY != null && (
              <line
                x1={CHART_PADDING}
                y1={chart.zeroY}
                x2={CHART_WIDTH - CHART_PADDING}
                y2={chart.zeroY}
                className="measurement__chart-zero"
              />
            )}
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
            <span>
              {rangeLabel}: {config.formatRange(chart.valueRange.min, chart.valueRange.max, mode)}
            </span>
          </div>
        </>
      ) : (
        <p className="measurement__chart-empty">{emptyMessage}</p>
      )}
    </div>
  )
}
