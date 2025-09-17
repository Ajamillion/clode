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
  metrics: Record<string, ToleranceMetricStats>
}
