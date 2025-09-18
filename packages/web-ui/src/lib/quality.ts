import { getGPUTier } from 'detect-gpu'

export type QualityKey = 'mobile' | 'desktop' | 'workstation'

export type QualityPreset = {
  meshResolution: number
  pressureFieldRes: number
  shadows: boolean | 'soft'
  postProcessing: boolean | 'full'
  maxParticles: number
  volumetricRendering?: boolean
}

export const qualityPresets: Record<QualityKey, QualityPreset> = {
  mobile: {
    meshResolution: 64,
    pressureFieldRes: 64,
    shadows: false,
    postProcessing: false,
    maxParticles: 2000
  },
  desktop: {
    meshResolution: 256,
    pressureFieldRes: 128,
    shadows: 'soft',
    postProcessing: true,
    maxParticles: 20000
  },
  workstation: {
    meshResolution: 512,
    pressureFieldRes: 256,
    shadows: 'soft',
    postProcessing: 'full',
    maxParticles: 120000,
    volumetricRendering: false
  }
}

export async function detectQuality(): Promise<QualityKey> {
  const tier = await getGPUTier()
  if (tier.tier >= 3) return 'workstation'
  if (tier.tier >= 2) return 'desktop'
  return 'mobile'
}
