import type { OptimizationRun, ToleranceReport, ToleranceMetricStats } from '@types/index'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

const DEFAULT_DRIVER = {
  fs_hz: 32,
  qts: 0.39,
  vas_l: 75,
  re_ohm: 3.2,
  bl_t_m: 15.5,
  mms_kg: 0.125,
  sd_m2: 0.052,
  le_h: 0.0007,
}

type ToleranceRequest = {
  endpoint: string
  body: Record<string, unknown>
  cacheKey: string
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function ventedPortDesign(volume: number) {
  const safeVolume = Math.max(volume, 10)
  let diameter = clamp(0.0018 * safeVolume + 0.065, 0.06, 0.15)
  const area = Math.PI * (diameter / 2) ** 2
  const count = safeVolume >= 85 ? 2 : 1
  if (count > 1) {
    diameter = Math.sqrt(area / count / Math.PI) * 2
  }
  const length = clamp(0.0032 * safeVolume + 0.18, 0.16, 0.48)
  return {
    volume_l: safeVolume,
    leakage_q: 9.5,
    port: {
      diameter_m: diameter,
      length_m: length,
      count,
      flare_factor: 1.6,
      loss_q: 18,
    },
  }
}

export function buildToleranceRequest(run: OptimizationRun | null, iterations = 200): ToleranceRequest | null {
  if (!run || run.status !== 'succeeded') return null
  const alignment = (run.result?.alignment ?? '').toLowerCase()
  const metrics = run.result?.metrics
  const volume = metrics?.volume_l
  if (typeof volume !== 'number' || !Number.isFinite(volume)) {
    return null
  }

  const driveVoltage = (() => {
    const metricsValue = metrics?.safe_drive_voltage_v
    if (typeof metricsValue === 'number' && Number.isFinite(metricsValue)) {
      return metricsValue
    }
    const summaryValue = run.result?.summary?.safe_drive_voltage_v
    if (typeof summaryValue === 'number' && Number.isFinite(summaryValue)) {
      return summaryValue
    }
    return 2.83
  })()

  if (alignment === 'vented') {
    const design = ventedPortDesign(volume)
    return {
      endpoint: '/simulate/vented/tolerances',
      cacheKey: `vented-${run.id}-${volume.toFixed(2)}-${driveVoltage.toFixed(2)}`,
      body: {
        driver: DEFAULT_DRIVER,
        box: design,
        iterations,
        drive_voltage: driveVoltage,
        mic_distance_m: 1,
        tolerances: null,
        excursion_limit: 1,
        port_velocity_limit_ms: 20,
      },
    }
  }

  return {
    endpoint: '/simulate/sealed/tolerances',
    cacheKey: `sealed-${run.id}-${volume.toFixed(2)}-${driveVoltage.toFixed(2)}`,
    body: {
      driver: DEFAULT_DRIVER,
      box: {
        volume_l: Math.max(volume, 5),
        leakage_q: 15,
      },
      iterations,
      drive_voltage: driveVoltage,
      mic_distance_m: 1,
      tolerances: null,
      excursion_limit: 1,
    },
  }
}

function normaliseMetricStats(raw: unknown): ToleranceMetricStats | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const read = (key: string) => {
    const value = Number(obj[key])
    return Number.isFinite(value) ? value : null
  }
  const mean = read('mean')
  const stddev = read('stddev')
  const min = read('min')
  const max = read('max')
  const p05 = read('p05')
  const p95 = read('p95')
  if ([mean, stddev, min, max, p05, p95].some((value) => value == null)) {
    return null
  }
  return {
    mean: mean!,
    stddev: stddev!,
    min: min!,
    max: max!,
    p05: p05!,
    p95: p95!,
  }
}

function normaliseMetrics(raw: unknown): Record<string, ToleranceMetricStats> {
  if (!raw || typeof raw !== 'object') return {}
  const metrics: Record<string, ToleranceMetricStats> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    const stats = normaliseMetricStats(value)
    if (stats) {
      metrics[key] = stats
    }
  }
  return metrics
}

export async function fetchToleranceReport(request: ToleranceRequest): Promise<ToleranceReport> {
  const response = await fetch(`${API_BASE}${request.endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request.body),
  })
  if (!response.ok) {
    throw new Error(`Tolerance request failed: ${response.status}`)
  }
  const payload = await response.json()
  const baselineRaw = payload?.baseline
  const baseline: Record<string, number | null> = {}
  if (baselineRaw && typeof baselineRaw === 'object') {
    for (const [key, value] of Object.entries(baselineRaw as Record<string, unknown>)) {
      baseline[key] = typeof value === 'number' && Number.isFinite(value) ? value : null
    }
  }
  const tolerancesRaw = payload?.tolerances
  const tolerances: Record<string, number> = {}
  if (tolerancesRaw && typeof tolerancesRaw === 'object') {
    for (const [key, value] of Object.entries(tolerancesRaw as Record<string, unknown>)) {
      const num = Number(value)
      if (!Number.isNaN(num)) {
        tolerances[key] = num
      }
    }
  }
  return {
    alignment: typeof payload?.alignment === 'string' ? payload.alignment : 'sealed',
    runs: Number(payload?.runs) || 0,
    baseline,
    tolerances,
    excursion_limit_ratio: Number(payload?.excursion_limit_ratio) || 1,
    excursion_exceedance_rate: Number(payload?.excursion_exceedance_rate) || 0,
    port_velocity_limit_ms: typeof payload?.port_velocity_limit_ms === 'number' ? payload.port_velocity_limit_ms : null,
    port_velocity_exceedance_rate:
      typeof payload?.port_velocity_exceedance_rate === 'number' ? payload.port_velocity_exceedance_rate : null,
    worst_case_spl_delta_db:
      typeof payload?.worst_case_spl_delta_db === 'number' ? payload.worst_case_spl_delta_db : null,
    metrics: normaliseMetrics(payload?.metrics),
  }
}
