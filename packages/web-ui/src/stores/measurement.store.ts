import { create } from 'zustand'
import {
  buildComparisonCsv,
  buildMeasurementRequest,
  fetchMeasurementComparison,
  previewMeasurement,
  synthesiseMeasurementFromRun,
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
  minFrequencyHz: number | null
  maxFrequencyHz: number | null
  smoothingFraction: number | null
  previewFromFile: (file: File) => Promise<void>
  generateSynthetic: (run: OptimizationRun | null) => void
  compareWithRun: (run: OptimizationRun | null) => Promise<void>
  clearComparison: () => void
  reset: () => void
  setFrequencyBand: (minHz: number | null, maxHz: number | null) => void
  setSmoothingFraction: (fraction: number | null) => void
  exportComparisonCsv: () => void
}

const baseState: Pick<
  MeasurementState,
  'preview' | 'previewSource' | 'comparison' | 'lastRunId' | 'lastComparedAt' | 'loading' | 'error' | 'minFrequencyHz' | 'maxFrequencyHz' | 'smoothingFraction'
> = {
  preview: null,
  previewSource: null,
  comparison: null,
  lastRunId: null,
  lastComparedAt: null,
  loading: false,
  error: null,
  minFrequencyHz: null,
  maxFrequencyHz: null,
  smoothingFraction: null,
}

function toErrorMessage(error: unknown) {
  if (error instanceof Error) return error.message
  return typeof error === 'string' ? error : 'Unexpected measurement error'
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
    const minFrequencyHz = get().minFrequencyHz
    const maxFrequencyHz = get().maxFrequencyHz
    const smoothingFraction = get().smoothingFraction
    if (!run || run.status !== 'succeeded') {
      set({ error: 'Comparison requires a completed optimisation run and a measurement preview.', loading: false })
      return
    }
    if (!measurement || measurement.frequency_hz.length === 0) {
      set({ error: 'Comparison requires a completed optimisation run and a measurement preview.', loading: false })
      return
    }
    const bandedRequest = buildMeasurementRequest(run, measurement, {
      band: { minHz: minFrequencyHz, maxHz: maxFrequencyHz },
      smoothingFraction,
    })
    if (!bandedRequest) {
      set({ error: 'Comparison request could not be created.', loading: false })
      return
    }
    set({ loading: true, error: null })
    try {
      const comparison = await fetchMeasurementComparison(bandedRequest)
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
  setFrequencyBand: (minHz, maxHz) => {
    const sanitize = (value: number | null) => {
      if (value == null) return null
      if (!Number.isFinite(value) || value <= 0) return null
      return value
    }
    let minValue = sanitize(minHz)
    let maxValue = sanitize(maxHz)
    if (minValue != null && maxValue != null && minValue > maxValue) {
      ;[minValue, maxValue] = [maxValue, minValue]
    }
    set({ minFrequencyHz: minValue, maxFrequencyHz: maxValue })
  },
  setSmoothingFraction: (fraction) => {
    if (fraction == null) {
      set({ smoothingFraction: null })
      return
    }
    const value = Number(fraction)
    if (!Number.isFinite(value) || value <= 0) {
      set({ smoothingFraction: null })
      return
    }
    set({ smoothingFraction: value })
  },
  exportComparisonCsv: () => {
    const preview = get().preview
    const comparison = get().comparison
    const csv = buildComparisonCsv(preview, comparison)
    if (!csv) {
      set({ error: 'Export requires a previewed measurement and comparison results.' })
      return
    }
    set({ error: null })
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      console.warn('Comparison CSV export is only available in the browser environment.')
      return
    }
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').replace('T', '_')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `measurement-comparison-${timestamp}.csv`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  },
}))
