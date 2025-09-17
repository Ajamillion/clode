import type {
  MeasurementComparison,
  MeasurementDelta,
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

type NullableNumberRecord = Record<string, number | null>

type ComparisonPayload = {
  summary?: NullableNumberRecord
  prediction?: MeasurementTrace | null
  delta?: MeasurementDelta | null
  stats?: MeasurementStats | null
}

function asNumberArray(value: unknown): number[] | null {
  if (!Array.isArray(value)) return null
  const arr = value
    .map((entry) => Number(entry))
    .filter((entry) => Number.isFinite(entry))
  return arr.length ? arr : null
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
    spl_rmse_db: read('spl_rmse_db'),
    spl_bias_db: read('spl_bias_db'),
    max_spl_delta_db: read('max_spl_delta_db'),
    phase_rmse_deg: read('phase_rmse_deg'),
    impedance_mag_rmse_ohm: read('impedance_mag_rmse_ohm'),
  }
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
  const alignment = (run.result?.alignment ?? 'sealed').toLowerCase()
  const baseBody = {
    driver: DEFAULT_DRIVER,
    measurement: serialiseMeasurement(measurement),
    drive_voltage: driveVoltage,
    mic_distance_m: 1,
  }
  if (alignment === 'vented') {
    return {
      endpoint: '/measurements/vented/compare',
      body: {
        ...baseBody,
        box: ventedPortDesign(volume),
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
  return comparison
}
