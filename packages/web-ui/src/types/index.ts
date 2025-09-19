export type MeshData = {
  vertices: Float32Array
  indices: Uint32Array
}

export type AcousticNode = {
  x: number
  y: number
  z: number
  amp: number
}

export type IterationMetrics = {
  iter: number
  loss?: number
  gradNorm?: number
  topology?: string
  timestamp?: number
  metrics?: Record<string, number>
}

export type AlignmentPreference = 'sealed' | 'vented' | 'auto'

export type OptParams = {
  targetSpl: number
  maxVolume: number
  weightLow: number
  weightMid: number
  preferAlignment?: AlignmentPreference
}

export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export type HybridDirectivity = {
  angles_deg: number[]
  response_db: number[][]
  index_db: number[]
}

export type OptimizationRunResult = {
  history?: IterationMetrics[]
  convergence?: {
    converged?: boolean
    iterations?: number
    finalLoss?: number
    cpuTime?: number
    solution?: Record<string, unknown>
  }
  summary?: Record<string, number | null>
  response?: Record<string, number[]>
  metrics?: Record<string, number>
  alignment?: string
  directivity?: HybridDirectivity | null
}

export type OptimizationRun = {
  id: string
  status: RunStatus
  created_at: number
  updated_at: number
  params: Record<string, unknown>
  result?: OptimizationRunResult | null
  error?: string | null
}

export type RunStatusCounts = Partial<Record<RunStatus, number>>

export type RunStats = {
  total: number
  counts: RunStatusCounts
}

export type ToleranceMetricStats = {
  mean: number
  stddev: number
  min: number
  max: number
  p05: number
  p95: number
}

export type ToleranceReport = {
  alignment: string
  runs: number
  baseline: Record<string, number | null>
  tolerances: Record<string, number>
  excursion_limit_ratio: number
  excursion_exceedance_rate: number
  port_velocity_limit_ms?: number | null
  port_velocity_exceedance_rate?: number | null
  worst_case_spl_delta_db?: number | null
  risk_rating: 'low' | 'moderate' | 'high'
  risk_factors: string[]
  metrics: Record<string, ToleranceMetricStats>
}

export type MeasurementTrace = {
  frequency_hz: number[]
  spl_db?: number[]
  phase_deg?: number[]
  impedance_real?: number[]
  impedance_imag?: number[]
  thd_percent?: number[]
}

export type MeasurementDelta = {
  frequency_hz: number[]
  spl_delta_db?: number[]
  phase_delta_deg?: number[]
  impedance_delta_ohm?: number[]
  thd_delta_percent?: number[]
}

export type MeasurementStats = {
  sample_count: number
  spl_rmse_db?: number | null
  spl_mae_db?: number | null
  spl_bias_db?: number | null
  spl_median_abs_dev_db?: number | null
  spl_std_dev_db?: number | null
  spl_pearson_r?: number | null
  spl_r_squared?: number | null
  spl_p95_abs_error_db?: number | null
  spl_highest_delta_db?: number | null
  spl_lowest_delta_db?: number | null
  max_spl_delta_db?: number | null
  phase_rmse_deg?: number | null
  impedance_mag_rmse_ohm?: number | null
}

export type MeasurementFrequencyBand = {
  min_hz: number | null
  max_hz: number | null
}

export type MeasurementDiagnosis = {
  overall_bias_db?: number | null
  recommended_level_trim_db?: number | null
  low_band_bias_db?: number | null
  mid_band_bias_db?: number | null
  high_band_bias_db?: number | null
  tuning_shift_hz?: number | null
  recommended_port_length_m?: number | null
  recommended_port_length_scale?: number | null
  leakage_hint?: 'lower_q' | 'raise_q' | null
  notes?: string[]
}

export type MeasurementCalibrationInterval = {
  lower: number
  upper: number
  confidence: number
}

export type MeasurementCalibrationParameter = {
  mean: number
  variance: number
  stddev: number
  prior_mean: number
  prior_variance: number
  observation?: number | null
  observation_variance?: number | null
  credible_interval?: MeasurementCalibrationInterval | null
  update_weight: number
}

export type MeasurementCalibration = {
  level_trim_db?: MeasurementCalibrationParameter | null
  port_length_scale?: MeasurementCalibrationParameter | null
  leakage_q_scale?: MeasurementCalibrationParameter | null
  notes?: string[]
}

export type MeasurementCalibrationOverrides = {
  drive_voltage_scale?: number | null
  drive_voltage_v?: number | null
  port_length_scale?: number | null
  port_length_m?: number | null
  leakage_q_scale?: number | null
  leakage_q?: number | null
}

export type MeasurementCalibratedInputs = {
  drive_voltage_v?: number | null
  leakage_q?: number | null
  port_length_m?: number | null
}

export type MeasurementCalibratedResult = {
  inputs?: MeasurementCalibratedInputs | null
  summary?: Record<string, number | null>
  prediction?: MeasurementTrace | null
  delta?: MeasurementDelta | null
  stats?: MeasurementStats | null
  diagnosis?: MeasurementDiagnosis | null
}

export type MeasurementComparison = {
  summary?: Record<string, number | null>
  prediction?: MeasurementTrace | null
  delta?: MeasurementDelta | null
  stats?: MeasurementStats | null
  diagnosis?: MeasurementDiagnosis | null
  calibration?: MeasurementCalibration | null
  calibration_overrides?: MeasurementCalibrationOverrides | null
  frequency_band?: MeasurementFrequencyBand | null
  calibrated?: MeasurementCalibratedResult | null
  smoothing_fraction?: number | null
}
