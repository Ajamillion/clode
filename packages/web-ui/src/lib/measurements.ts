import type {
  MeasurementComparison,
  MeasurementCalibration,
  MeasurementCalibrationParameter,
  MeasurementCalibrationOverrides,
  MeasurementCalibratedResult,
  MeasurementCalibratedInputs,
  MeasurementDelta,
  MeasurementDiagnosis,
  MeasurementFrequencyBand,
  MeasurementStats,
  MeasurementTrace,
  OptimizationRun,
} from '@types/index'
import { DEFAULT_DRIVER, ventedPortDesign } from '@lib/tolerances'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export type MeasurementRequest = {
  endpoint: string
  body: Record<string, unknown>
}

type Lookup = Map<string, number>

type NullableNumberRecord = Record<string, number | null>

type ComparisonPayload = {
  summary?: NullableNumberRecord
  prediction?: MeasurementTrace | null
  delta?: MeasurementDelta | null
  stats?: MeasurementStats | null
  diagnosis?: MeasurementDiagnosis | null
  calibration?: MeasurementCalibration | null
  calibration_overrides?: MeasurementCalibrationOverrides | null
  calibrated?: MeasurementCalibratedResult | null
  smoothing_fraction?: number | null
}

function asNumberArray(value: unknown): number[] | null {
  if (!Array.isArray(value)) return null
  const arr = value
    .map((entry) => Number(entry))
    .filter((entry) => Number.isFinite(entry))
  return arr.length ? arr : null
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function frequencyKey(value: number | null | undefined): string | null {
  if (!isFiniteNumber(value)) return null
  return value.toFixed(6)
}

function createLookup(frequency: number[] | undefined, values: number[] | undefined): Lookup | null {
  if (!frequency || !values) return null
  const len = Math.min(frequency.length, values.length)
  const lookup: Lookup = new Map()
  for (let i = 0; i < len; i += 1) {
    const key = frequencyKey(frequency[i])
    const value = values[i]
    if (key && isFiniteNumber(value)) {
      lookup.set(key, value)
    }
  }
  return lookup.size > 0 ? lookup : null
}

function valueAt(values: number[] | undefined, index: number): number | null {
  if (!values || index < 0 || index >= values.length) return null
  const value = values[index]
  return isFiniteNumber(value) ? value : null
}

function lookupValue(
  index: number,
  frequency: number,
  values: number[] | undefined,
  lookup: Lookup | null,
): number | null {
  const key = frequencyKey(frequency)
  if (key && lookup?.has(key)) {
    const value = lookup.get(key)
    return isFiniteNumber(value) ? value : null
  }
  return valueAt(values, index)
}

function magnitude(real: number | null, imag: number | null): number | null {
  if (real == null || imag == null) return null
  return Math.sqrt(real * real + imag * imag)
}

function csvValue(value: number | null): string {
  if (!isFiniteNumber(value)) return ''
  const normalized = Math.abs(value) < 1e-12 ? 0 : value
  return String(normalized)
}

function serialiseMeasurement(trace: MeasurementTrace): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    frequency_hz: [...trace.frequency_hz],
  }
  if (trace.spl_db?.length) {
    payload.spl_db = [...trace.spl_db]
  }
  if (trace.phase_deg?.length) {
    payload.phase_deg = [...trace.phase_deg]
  }
  if (trace.impedance_real?.length && trace.impedance_imag?.length) {
    const len = Math.min(trace.impedance_real.length, trace.impedance_imag.length)
    payload.impedance_real = trace.impedance_real.slice(0, len)
    payload.impedance_imag = trace.impedance_imag.slice(0, len)
  }
  if (trace.thd_percent?.length) {
    payload.thd_percent = [...trace.thd_percent]
  }
  return payload
}

function normaliseNumberRecord(raw: unknown): NullableNumberRecord | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const obj = raw as Record<string, unknown>
  const result: NullableNumberRecord = {}
  for (const [key, value] of Object.entries(obj)) {
    if (value === null) {
      result[key] = null
      continue
    }
    const num = Number(value)
    if (!Number.isNaN(num)) {
      result[key] = num
    }
  }
  return Object.keys(result).length ? result : undefined
}

export function normaliseMeasurementTrace(raw: unknown): MeasurementTrace | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const frequency = asNumberArray(obj.frequency_hz)
  if (!frequency) return null
  const trace: MeasurementTrace = {
    frequency_hz: frequency,
  }
  const spl = asNumberArray(obj.spl_db)
  if (spl?.length === frequency.length) {
    trace.spl_db = spl
  }
  const phase = asNumberArray(obj.phase_deg)
  if (phase?.length === frequency.length) {
    trace.phase_deg = phase
  }
  const impReal = asNumberArray(obj.impedance_real)
  const impImag = asNumberArray(obj.impedance_imag)
  if (impReal && impImag && impReal.length === impImag.length) {
    trace.impedance_real = impReal
    trace.impedance_imag = impImag
  }
  const thd = asNumberArray(obj.thd_percent)
  if (thd?.length === frequency.length) {
    trace.thd_percent = thd
  }
  return trace
}

export function normaliseMeasurementDelta(raw: unknown): MeasurementDelta | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const frequency = asNumberArray(obj.frequency_hz)
  if (!frequency) return null
  const delta: MeasurementDelta = {
    frequency_hz: frequency,
  }
  const spl = asNumberArray(obj.spl_delta_db)
  if (spl?.length === frequency.length) {
    delta.spl_delta_db = spl
  }
  const phase = asNumberArray(obj.phase_delta_deg)
  if (phase?.length === frequency.length) {
    delta.phase_delta_deg = phase
  }
  const impedance = asNumberArray(obj.impedance_delta_ohm)
  if (impedance?.length === frequency.length) {
    delta.impedance_delta_ohm = impedance
  }
  const thd = asNumberArray(obj.thd_delta_percent)
  if (thd?.length === frequency.length) {
    delta.thd_delta_percent = thd
  }
  return delta
}

export function normaliseMeasurementStats(raw: unknown): MeasurementStats | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const sampleCount = Number(obj.sample_count)
  if (!Number.isFinite(sampleCount)) return null
  const read = (key: string) => {
    const value = obj[key]
    if (value == null) return null
    const num = Number(value)
    return Number.isFinite(num) ? num : null
  }
  return {
    sample_count: Math.trunc(sampleCount),
    minimum_frequency_hz: read('minimum_frequency_hz'),
    maximum_frequency_hz: read('maximum_frequency_hz'),
    spl_rmse_db: read('spl_rmse_db'),
    spl_mae_db: read('spl_mae_db'),
    spl_bias_db: read('spl_bias_db'),
    spl_median_abs_dev_db: read('spl_median_abs_dev_db'),
    spl_interquartile_range_db: read('spl_interquartile_range_db'),
    spl_std_dev_db: read('spl_std_dev_db'),
    spl_pearson_r: read('spl_pearson_r'),
    spl_r_squared: read('spl_r_squared'),
    spl_p95_abs_error_db: read('spl_p95_abs_error_db'),
    spl_highest_delta_db: read('spl_highest_delta_db'),
    spl_lowest_delta_db: read('spl_lowest_delta_db'),
    max_spl_delta_db: read('max_spl_delta_db'),
    phase_rmse_deg: read('phase_rmse_deg'),
    impedance_mag_rmse_ohm: read('impedance_mag_rmse_ohm'),
  }
}

export function normaliseFrequencyBand(raw: unknown): MeasurementFrequencyBand | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const min = Number(obj.min_hz)
  const max = Number(obj.max_hz)
  return {
    min_hz: Number.isFinite(min) ? min : null,
    max_hz: Number.isFinite(max) ? max : null,
  }
}

export function normaliseSmoothingFraction(raw: unknown): number | null {
  if (raw == null) return null
  const value = Number(raw)
  if (!Number.isFinite(value)) return null
  return value > 0 ? value : null
}

export function normaliseMeasurementDiagnosis(raw: unknown): MeasurementDiagnosis | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const read = (key: string) => {
    const value = obj[key]
    if (value == null) return null
    const num = Number(value)
    return Number.isFinite(num) ? num : null
  }
  const notesValue = obj.notes
  const notes = Array.isArray(notesValue)
    ? notesValue.map((entry) => String(entry)).filter((entry) => entry.length > 0)
    : undefined
  const diagnosis: MeasurementDiagnosis = {}
  const mappings: [keyof MeasurementDiagnosis, string][] = [
    ['overall_bias_db', 'overall_bias_db'],
    ['recommended_level_trim_db', 'recommended_level_trim_db'],
    ['low_band_bias_db', 'low_band_bias_db'],
    ['mid_band_bias_db', 'mid_band_bias_db'],
    ['high_band_bias_db', 'high_band_bias_db'],
    ['tuning_shift_hz', 'tuning_shift_hz'],
    ['recommended_port_length_m', 'recommended_port_length_m'],
    ['recommended_port_length_scale', 'recommended_port_length_scale'],
  ]
  for (const [target, source] of mappings) {
    const value = read(source)
    if (value != null) {
      diagnosis[target] = value
    }
  }
  const leakage = obj.leakage_hint
  if (leakage === 'lower_q' || leakage === 'raise_q') {
    diagnosis.leakage_hint = leakage
  }
  if (notes && notes.length) {
    diagnosis.notes = notes
  }
  return Object.keys(diagnosis).length ? diagnosis : null
}

function normaliseCalibratedInputs(raw: unknown): MeasurementCalibratedInputs | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const read = (key: string) => {
    const value = obj[key]
    if (value == null) return null
    const num = Number(value)
    return Number.isFinite(num) ? num : null
  }
  const inputs: MeasurementCalibratedInputs = {
    drive_voltage_v: read('drive_voltage_v'),
    leakage_q: read('leakage_q'),
    port_length_m: read('port_length_m'),
  }
  if (inputs.drive_voltage_v == null && inputs.leakage_q == null && inputs.port_length_m == null) {
    return null
  }
  return inputs
}

function normaliseCalibratedResult(raw: unknown): MeasurementCalibratedResult | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const result: MeasurementCalibratedResult = {
    inputs: normaliseCalibratedInputs(obj.inputs),
    summary: normaliseNumberRecord(obj.summary),
    prediction: normaliseMeasurementTrace(obj.prediction),
    delta: normaliseMeasurementDelta(obj.delta),
    stats: normaliseMeasurementStats(obj.stats),
    diagnosis: normaliseMeasurementDiagnosis(obj.diagnosis),
  }
  const hasData = Boolean(
    result.inputs ||
      result.summary ||
      result.prediction ||
      result.delta ||
      result.stats ||
      result.diagnosis,
  )
  return hasData ? result : null
}

function normaliseCalibrationParameter(raw: unknown): MeasurementCalibrationParameter | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const mean = Number(obj['mean'])
  const variance = Number(obj['variance'])
  if (!Number.isFinite(mean) || !Number.isFinite(variance)) return null
  const stddevRaw = Number(obj['stddev'])
  const stddev = Number.isFinite(stddevRaw) ? stddevRaw : Math.sqrt(Math.max(variance, 0))
  const priorMean = Number(obj['prior_mean'])
  const priorVariance = Number(obj['prior_variance'])
  const updateWeightRaw = Number(obj['update_weight'])
  const parameter: MeasurementCalibrationParameter = {
    mean,
    variance,
    stddev,
    prior_mean: Number.isFinite(priorMean) ? priorMean : 0,
    prior_variance: Number.isFinite(priorVariance) ? priorVariance : 0,
    update_weight: Number.isFinite(updateWeightRaw) ? Math.min(Math.max(updateWeightRaw, 0), 1) : 0,
  }
  const observation = obj['observation']
  if (typeof observation === 'number' && Number.isFinite(observation)) {
    parameter.observation = observation
  }
  const obsVar = obj['observation_variance']
  if (typeof obsVar === 'number' && Number.isFinite(obsVar)) {
    parameter.observation_variance = obsVar
  }
  const interval = obj['credible_interval']
  if (interval && typeof interval === 'object') {
    const info = interval as Record<string, unknown>
    const lower = Number(info.lower)
    const upper = Number(info.upper)
    const confidence = Number(info.confidence)
    if (Number.isFinite(lower) && Number.isFinite(upper) && Number.isFinite(confidence)) {
      parameter.credible_interval = {
        lower,
        upper,
        confidence,
      }
    }
  }
  return parameter
}

export function normaliseMeasurementCalibration(raw: unknown): MeasurementCalibration | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const calibration: MeasurementCalibration = {}
  const level = normaliseCalibrationParameter(obj['level_trim_db'])
  if (level) calibration.level_trim_db = level
  const port = normaliseCalibrationParameter(obj['port_length_scale'])
  if (port) calibration.port_length_scale = port
  const leakage = normaliseCalibrationParameter(obj['leakage_q_scale'])
  if (leakage) calibration.leakage_q_scale = leakage
  const notes = obj['notes']
  if (Array.isArray(notes)) {
    const clean = notes.map((entry) => String(entry)).filter((entry) => entry.length > 0)
    if (clean.length) calibration.notes = clean
  }
  return Object.keys(calibration).length ? calibration : null
}

export function normaliseMeasurementOverrides(raw: unknown): MeasurementCalibrationOverrides | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const overrides: MeasurementCalibrationOverrides = {}
  const keys: (keyof MeasurementCalibrationOverrides)[] = [
    'drive_voltage_scale',
    'drive_voltage_v',
    'port_length_scale',
    'port_length_m',
    'leakage_q_scale',
    'leakage_q',
  ]
  for (const key of keys) {
    const value = obj[key]
    if (value == null) {
      overrides[key] = null
      continue
    }
    const num = Number(value)
    if (Number.isFinite(num)) {
      overrides[key] = num
    }
  }
  return Object.keys(overrides).length ? overrides : null
}

export async function previewMeasurement(file: File): Promise<MeasurementTrace> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${API_BASE}/measurements/preview`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    throw new Error(`Preview failed: ${response.status}`)
  }
  const payload = await response.json().catch(() => null)
  const trace = normaliseMeasurementTrace((payload as Record<string, unknown> | null)?.measurement)
  if (!trace) {
    throw new Error('Measurement preview did not return a valid trace')
  }
  return trace
}

function deriveDriveVoltage(run: OptimizationRun | null): number {
  const metrics = run?.result?.metrics
  const summary = run?.result?.summary
  const candidates = [
    metrics?.safe_drive_voltage_v,
    summary?.safe_drive_voltage_v,
  ]
  for (const candidate of candidates) {
    const value = Number(candidate)
    if (Number.isFinite(value) && value > 0) {
      return value
    }
  }
  return 2.83
}

export function synthesiseMeasurementFromRun(run: OptimizationRun | null): MeasurementTrace | null {
  const response = run?.result?.response
  if (!response) return null
  const frequency = asNumberArray((response as Record<string, unknown>).frequency_hz)
  const spl = asNumberArray((response as Record<string, unknown>).spl_db)
  if (!frequency || !spl || frequency.length !== spl.length) return null
  const measurementSpl = spl.map((value, idx) => value - 1.4 + Math.sin(idx / 6) * 0.9)
  const trace: MeasurementTrace = {
    frequency_hz: frequency,
    spl_db: measurementSpl,
  }
  const impReal = asNumberArray((response as Record<string, unknown>).impedance_real)
  const impImag = asNumberArray((response as Record<string, unknown>).impedance_imag)
  if (impReal && impImag && impReal.length === frequency.length && impImag.length === frequency.length) {
    trace.impedance_real = impReal.map((value, idx) => value * (0.95 + 0.03 * Math.sin(idx / 9)))
    trace.impedance_imag = impImag.map((value, idx) => value * (0.9 + 0.05 * Math.cos(idx / 11)))
  }
  return trace
}

export function buildMeasurementRequest(
  run: OptimizationRun | null,
  measurement: MeasurementTrace | null,
  options?: { band?: { minHz: number | null; maxHz: number | null }; smoothingFraction?: number | null },
): MeasurementRequest | null {
  if (!run || run.status !== 'succeeded' || !measurement || measurement.frequency_hz.length === 0) {
    return null
  }
  const metrics = run.result?.metrics
  const volumeRaw = metrics?.volume_l ?? run.result?.summary?.volume_l
  const volume = Number(volumeRaw)
  if (!Number.isFinite(volume) || volume <= 0) {
    return null
  }
  const driveVoltage = deriveDriveVoltage(run)
  const sanitize = (value: number | null | undefined) => {
    if (value == null) return null
    const num = Number(value)
    if (!Number.isFinite(num) || num <= 0) return null
    return num
  }
  const band = options?.band
  let minFrequency = sanitize(band?.minHz)
  let maxFrequency = sanitize(band?.maxHz)
  if (minFrequency != null && maxFrequency != null && minFrequency > maxFrequency) {
    ;[minFrequency, maxFrequency] = [maxFrequency, minFrequency]
  }
  const smoothingFractionRaw = options?.smoothingFraction
  const smoothingFraction = (() => {
    if (smoothingFractionRaw == null) return null
    const value = Number(smoothingFractionRaw)
    if (!Number.isFinite(value) || value <= 0) return null
    return value
  })()
  const alignment = (run.result?.alignment ?? 'sealed').toLowerCase()
  const baseBody = {
    driver: DEFAULT_DRIVER,
    measurement: serialiseMeasurement(measurement),
    drive_voltage: driveVoltage,
    mic_distance_m: 1,
    ...(minFrequency ? { min_frequency_hz: minFrequency } : {}),
    ...(maxFrequency ? { max_frequency_hz: maxFrequency } : {}),
    ...(smoothingFraction ? { smoothing_fraction: smoothingFraction } : {}),
  }
  if (alignment === 'vented') {
    return {
      endpoint: '/measurements/vented/compare',
      body: {
        ...baseBody,
        box: ventedPortDesign(volume),
        apply_overrides: true,
      },
    }
  }
  return {
    endpoint: '/measurements/sealed/compare',
    body: {
      ...baseBody,
      box: {
        volume_l: Math.max(volume, 5),
        leakage_q: 15,
      },
      apply_overrides: true,
    },
  }
}

export async function fetchMeasurementComparison(
  request: MeasurementRequest,
): Promise<MeasurementComparison> {
  const response = await fetch(`${API_BASE}${request.endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request.body),
  })
  if (!response.ok) {
    throw new Error(`Measurement compare failed: ${response.status}`)
  }
  const payload = await response.json().catch(() => null)
  const data = payload as Record<string, unknown> | null
  const comparison: ComparisonPayload = {}
  comparison.summary = normaliseNumberRecord(data?.summary)
  comparison.prediction = normaliseMeasurementTrace(data?.prediction) ?? null
  comparison.delta = normaliseMeasurementDelta(data?.delta) ?? null
  comparison.stats = normaliseMeasurementStats(data?.stats) ?? null
  comparison.diagnosis = normaliseMeasurementDiagnosis(data?.diagnosis) ?? null
  comparison.calibration = normaliseMeasurementCalibration(data?.calibration) ?? null
  comparison.calibration_overrides = normaliseMeasurementOverrides(data?.calibration_overrides) ?? null
  comparison.frequency_band = normaliseFrequencyBand(data?.frequency_band) ?? null
  comparison.calibrated = normaliseCalibratedResult(data?.calibrated) ?? null
  comparison.smoothing_fraction = normaliseSmoothingFraction(data?.smoothing_fraction)
  return comparison
}

type Column = {
  header: string
  getter: (index: number, frequency: number) => number | null
}

export function buildComparisonCsv(
  measurement: MeasurementTrace | null,
  comparison: MeasurementComparison | null,
): string | null {
  if (!measurement || !comparison) return null
  const frequencyAxis = measurement.frequency_hz
  if (!Array.isArray(frequencyAxis) || frequencyAxis.length === 0) return null

  const prediction = comparison.prediction ?? null
  const delta = comparison.delta ?? null
  const calibratedPrediction = comparison.calibrated?.prediction ?? null
  const calibratedDelta = comparison.calibrated?.delta ?? null

  const predictionLookups = {
    spl: createLookup(prediction?.frequency_hz, prediction?.spl_db),
    phase: createLookup(prediction?.frequency_hz, prediction?.phase_deg),
    impReal: createLookup(prediction?.frequency_hz, prediction?.impedance_real),
    impImag: createLookup(prediction?.frequency_hz, prediction?.impedance_imag),
    thd: createLookup(prediction?.frequency_hz, prediction?.thd_percent),
  }

  const deltaLookups = {
    spl: createLookup(delta?.frequency_hz, delta?.spl_delta_db),
    phase: createLookup(delta?.frequency_hz, delta?.phase_delta_deg),
    impedance: createLookup(delta?.frequency_hz, delta?.impedance_delta_ohm),
    thd: createLookup(delta?.frequency_hz, delta?.thd_delta_percent),
  }

  const calibratedPredictionLookups = {
    spl: createLookup(calibratedPrediction?.frequency_hz, calibratedPrediction?.spl_db),
    phase: createLookup(calibratedPrediction?.frequency_hz, calibratedPrediction?.phase_deg),
    impReal: createLookup(calibratedPrediction?.frequency_hz, calibratedPrediction?.impedance_real),
    impImag: createLookup(calibratedPrediction?.frequency_hz, calibratedPrediction?.impedance_imag),
    thd: createLookup(calibratedPrediction?.frequency_hz, calibratedPrediction?.thd_percent),
  }

  const calibratedDeltaLookups = {
    spl: createLookup(calibratedDelta?.frequency_hz, calibratedDelta?.spl_delta_db),
    phase: createLookup(calibratedDelta?.frequency_hz, calibratedDelta?.phase_delta_deg),
    impedance: createLookup(calibratedDelta?.frequency_hz, calibratedDelta?.impedance_delta_ohm),
    thd: createLookup(calibratedDelta?.frequency_hz, calibratedDelta?.thd_delta_percent),
  }

  const columns: Column[] = [
    {
      header: 'frequency_hz',
      getter: (_index, frequency) => (Number.isFinite(frequency) ? frequency : null),
    },
    {
      header: 'measurement_spl_db',
      getter: (index) => valueAt(measurement.spl_db, index),
    },
    {
      header: 'prediction_spl_db',
      getter: (index, frequency) => lookupValue(index, frequency, prediction?.spl_db, predictionLookups.spl),
    },
    {
      header: 'delta_spl_db',
      getter: (index, frequency) => lookupValue(index, frequency, delta?.spl_delta_db, deltaLookups.spl),
    },
    {
      header: 'measurement_phase_deg',
      getter: (index) => valueAt(measurement.phase_deg, index),
    },
    {
      header: 'prediction_phase_deg',
      getter: (index, frequency) => lookupValue(index, frequency, prediction?.phase_deg, predictionLookups.phase),
    },
    {
      header: 'delta_phase_deg',
      getter: (index, frequency) => lookupValue(index, frequency, delta?.phase_delta_deg, deltaLookups.phase),
    },
    {
      header: 'measurement_impedance_real_ohm',
      getter: (index) => valueAt(measurement.impedance_real, index),
    },
    {
      header: 'measurement_impedance_imag_ohm',
      getter: (index) => valueAt(measurement.impedance_imag, index),
    },
    {
      header: 'measurement_impedance_magnitude_ohm',
      getter: (index) => magnitude(valueAt(measurement.impedance_real, index), valueAt(measurement.impedance_imag, index)),
    },
    {
      header: 'prediction_impedance_real_ohm',
      getter: (index, frequency) => lookupValue(index, frequency, prediction?.impedance_real, predictionLookups.impReal),
    },
    {
      header: 'prediction_impedance_imag_ohm',
      getter: (index, frequency) => lookupValue(index, frequency, prediction?.impedance_imag, predictionLookups.impImag),
    },
    {
      header: 'prediction_impedance_magnitude_ohm',
      getter: (index, frequency) => {
        const real = lookupValue(index, frequency, prediction?.impedance_real, predictionLookups.impReal)
        const imag = lookupValue(index, frequency, prediction?.impedance_imag, predictionLookups.impImag)
        return magnitude(real, imag)
      },
    },
    {
      header: 'delta_impedance_magnitude_ohm',
      getter: (index, frequency) => lookupValue(index, frequency, delta?.impedance_delta_ohm, deltaLookups.impedance),
    },
    {
      header: 'measurement_thd_percent',
      getter: (index) => valueAt(measurement.thd_percent, index),
    },
    {
      header: 'prediction_thd_percent',
      getter: (index, frequency) => lookupValue(index, frequency, prediction?.thd_percent, predictionLookups.thd),
    },
    {
      header: 'delta_thd_percent',
      getter: (index, frequency) => lookupValue(index, frequency, delta?.thd_delta_percent, deltaLookups.thd),
    },
  ]

  if (calibratedPrediction) {
    columns.push(
      {
        header: 'calibrated_prediction_spl_db',
        getter: (index, frequency) =>
          lookupValue(index, frequency, calibratedPrediction.spl_db, calibratedPredictionLookups.spl),
      },
      {
        header: 'calibrated_prediction_phase_deg',
        getter: (index, frequency) =>
          lookupValue(index, frequency, calibratedPrediction.phase_deg, calibratedPredictionLookups.phase),
      },
      {
        header: 'calibrated_prediction_impedance_real_ohm',
        getter: (index, frequency) =>
          lookupValue(index, frequency, calibratedPrediction.impedance_real, calibratedPredictionLookups.impReal),
      },
      {
        header: 'calibrated_prediction_impedance_imag_ohm',
        getter: (index, frequency) =>
          lookupValue(index, frequency, calibratedPrediction.impedance_imag, calibratedPredictionLookups.impImag),
      },
      {
        header: 'calibrated_prediction_impedance_magnitude_ohm',
        getter: (index, frequency) => {
          const real = lookupValue(index, frequency, calibratedPrediction.impedance_real, calibratedPredictionLookups.impReal)
          const imag = lookupValue(index, frequency, calibratedPrediction.impedance_imag, calibratedPredictionLookups.impImag)
          return magnitude(real, imag)
        },
      },
      {
        header: 'calibrated_prediction_thd_percent',
        getter: (index, frequency) =>
          lookupValue(index, frequency, calibratedPrediction.thd_percent, calibratedPredictionLookups.thd),
      },
    )
  }

  if (calibratedDelta) {
    columns.push(
      {
        header: 'calibrated_delta_spl_db',
        getter: (index, frequency) => lookupValue(index, frequency, calibratedDelta.spl_delta_db, calibratedDeltaLookups.spl),
      },
      {
        header: 'calibrated_delta_phase_deg',
        getter: (index, frequency) =>
          lookupValue(index, frequency, calibratedDelta.phase_delta_deg, calibratedDeltaLookups.phase),
      },
      {
        header: 'calibrated_delta_impedance_magnitude_ohm',
        getter: (index, frequency) =>
          lookupValue(index, frequency, calibratedDelta.impedance_delta_ohm, calibratedDeltaLookups.impedance),
      },
      {
        header: 'calibrated_delta_thd_percent',
        getter: (index, frequency) => lookupValue(index, frequency, calibratedDelta.thd_delta_percent, calibratedDeltaLookups.thd),
      },
    )
  }

  const header = columns.map((column) => column.header).join(',')
  const rows: string[] = [header]

  for (let index = 0; index < frequencyAxis.length; index += 1) {
    const frequency = frequencyAxis[index]
    const values = columns.map((column) => csvValue(column.getter(index, frequency)))
    rows.push(values.join(','))
  }

  return rows.join('\n')
}
