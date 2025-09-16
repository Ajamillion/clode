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

export type OptParams = Record<string, number>

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
