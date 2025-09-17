import { create } from 'zustand'
import {
  buildMeasurementRequest,
  fetchMeasurementComparison,
  previewMeasurement,
  synthesiseMeasurementFromRun,
  type MeasurementRequest,
} from '@lib/measurements'
import type { MeasurementComparison, MeasurementTrace, OptimizationRun } from '@types/index'

type MeasurementSource = 'synthetic' | 'upload'

type MeasurementState = {
  preview: MeasurementTrace | null
  previewSource: MeasurementSource | null
  comparison: MeasurementComparison | null
  lastRunId: string | null
  lastComparedAt: number | null
  loading: boolean
  error: string | null
  previewFromFile: (file: File) => Promise<void>
  generateSynthetic: (run: OptimizationRun | null) => void
  compareWithRun: (run: OptimizationRun | null) => Promise<void>
  clearComparison: () => void
  reset: () => void
}

const baseState: Pick<
  MeasurementState,
  'preview' | 'previewSource' | 'comparison' | 'lastRunId' | 'lastComparedAt' | 'loading' | 'error'
> = {
  preview: null,
  previewSource: null,
  comparison: null,
  lastRunId: null,
  lastComparedAt: null,
  loading: false,
  error: null,
}

function toErrorMessage(error: unknown) {
  if (error instanceof Error) return error.message
  return typeof error === 'string' ? error : 'Unexpected measurement error'
}

function assertRequest(
  run: OptimizationRun | null,
  measurement: MeasurementTrace | null,
): MeasurementRequest | null {
  if (!run || run.status !== 'succeeded') {
    return null
  }
  if (!measurement || measurement.frequency_hz.length === 0) {
    return null
  }
  return buildMeasurementRequest(run, measurement)
}

export const useMeasurement = create<MeasurementState>((set, get) => ({
  ...baseState,
  previewFromFile: async (file) => {
    set({ loading: true, error: null })
    try {
      const trace = await previewMeasurement(file)
      set({
        preview: trace,
        previewSource: 'upload',
        comparison: null,
        lastRunId: null,
        lastComparedAt: null,
        loading: false,
      })
    } catch (error) {
      set({ loading: false, error: toErrorMessage(error) })
    }
  },
  generateSynthetic: (run) => {
    if (!run || run.status !== 'succeeded') {
      set({ error: 'Generate a measurement from a completed optimisation run first.', loading: false })
      return
    }
    const trace = synthesiseMeasurementFromRun(run)
    if (!trace) {
      set({ error: 'Run response does not include enough data to synthesise a measurement.', loading: false })
      return
    }
    set({
      preview: trace,
      previewSource: 'synthetic',
      comparison: null,
      lastRunId: null,
      lastComparedAt: null,
      error: null,
      loading: false,
    })
  },
  compareWithRun: async (run) => {
    const measurement = get().preview
    const request = assertRequest(run, measurement)
    if (!request || !run) {
      set({ error: 'Comparison requires a completed optimisation run and a measurement preview.', loading: false })
      return
    }
    set({ loading: true, error: null })
    try {
      const comparison = await fetchMeasurementComparison(request)
      set({
        comparison,
        lastRunId: run.id,
        lastComparedAt: Date.now(),
        loading: false,
      })
    } catch (error) {
      set({ loading: false, error: toErrorMessage(error) })
    }
  },
  clearComparison: () => {
    set({ comparison: null, lastRunId: null, lastComparedAt: null })
  },
  reset: () => set({ ...baseState }),
}))
