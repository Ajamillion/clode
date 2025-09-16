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
