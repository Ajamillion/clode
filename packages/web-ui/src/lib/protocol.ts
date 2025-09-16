import { z } from 'zod'

const numericArray = z.union([
  z.array(z.number()),
  z.instanceof(Float32Array).transform((arr) => Array.from(arr)),
  z.instanceof(Float64Array).transform((arr) => Array.from(arr)),
  z.instanceof(Int16Array).transform((arr) => Array.from(arr as Int16Array).map(Number)),
  z.instanceof(Int32Array).transform((arr) => Array.from(arr as Int32Array).map(Number)),
  z.instanceof(Uint8Array).transform((arr) => Array.from(arr as Uint8Array).map(Number)),
  z.instanceof(Uint16Array).transform((arr) => Array.from(arr as Uint16Array).map(Number)),
  z.instanceof(Uint32Array).transform((arr) => Array.from(arr as Uint32Array).map(Number))
])

const iterationSchema = z.object({
  type: z.literal('ITERATION'),
  data: z.object({
    iter: z.number().int().nonnegative().optional(),
    loss: z.number().optional(),
    gradNorm: z.number().optional(),
    topology: z.string().optional(),
    timestamp: z.number().optional(),
    metrics: z.record(z.number()).optional(),
    constraints: z.record(z.number()).optional(),
    designVars: numericArray.optional(),
    frequency: numericArray.optional(),
    spl: numericArray.optional()
  })
})

const topologySchema = z.object({
  type: z.literal('TOPOLOGY_SWITCH'),
  from: z.string().optional(),
  to: z.string()
})

const violationSchema = z.object({
  type: z.literal('CONSTRAINT_VIOLATION'),
  constraint: z.string(),
  location: z.any().optional(),
  severity: z.number().optional()
})

const convergenceSchema = z.object({
  type: z.literal('CONVERGENCE'),
  data: z.object({
    converged: z.boolean().optional(),
    iterations: z.number().int().nonnegative().optional(),
    finalLoss: z.number().optional(),
    cpuTime: z.number().optional(),
    solution: z.record(z.any()).optional()
  })
})

const heartbeatSchema = z.object({
  type: z.literal('HEARTBEAT'),
  at: z.number()
})

export const solverMessageSchema = z.discriminatedUnion('type', [
  iterationSchema,
  topologySchema,
  violationSchema,
  convergenceSchema,
  heartbeatSchema
])

export type SolverMessage = z.infer<typeof solverMessageSchema>
export type IterationMessage = z.infer<typeof iterationSchema>["data"]
export type ConstraintViolationMessage = z.infer<typeof violationSchema>
export type TopologySwitchMessage = z.infer<typeof topologySchema>
export type ConvergenceMessage = z.infer<typeof convergenceSchema>["data"]

export function parseSolverMessage(payload: unknown): SolverMessage | null {
  const result = solverMessageSchema.safeParse(payload)
  if (!result.success) {
    if (import.meta.env?.DEV) {
      console.warn('Unrecognized solver payload', result.error.flatten())
    }
    return null
  }
  return result.data
}
