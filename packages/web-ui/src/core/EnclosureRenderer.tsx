import { useEffect, useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { EffectComposer, SSAO, Bloom } from '@react-three/postprocessing'
import { GPU } from 'gpu.js'
import { EnclosureMesh } from '@components/EnclosureMesh'
import { PressureField } from '@components/PressureField'
import { PortFlowLines } from '@components/PortFlowLines'
import { detectQuality, qualityPresets, type QualityKey, type QualityPreset } from '@lib/quality'
import type { MeshData, AcousticNode } from '@types/index'

type Props = {
  geometry: MeshData
  acousticNodes: AcousticNode[]
  currentFreq: number
}

export function EnclosureRenderer({ geometry, acousticNodes, currentFreq }: Props) {
  const gpuRef = useRef<GPU | null>(null)
  const kernelRef = useRef<ReturnType<GPU['createKernel']> | null>(null)
  const [qualityKey, setQualityKey] = useState<QualityKey>('desktop')
  const [res, setRes] = useState(128)
  const [zSlice] = useState(0.5)
  const [field, setField] = useState<Float32Array>(() => new Float32Array(128 * 128))

  useEffect(() => {
    ;(async () => {
      const quality = await detectQuality()
      setQualityKey(quality)
      setRes(qualityPresets[quality].pressureFieldRes)
    })()
  }, [])

  useEffect(() => {
    const gpu = gpuRef.current ?? new GPU()
    gpuRef.current = gpu
    kernelRef.current?.destroy?.()
    const kernel = gpu
      .createKernel(function (nodes: Float32Array, freq: number, t: number, nSources: number, zSliceVal: number, resolution: number) {
        const x = this.thread.x / (resolution - 1)
        const y = this.thread.y / (resolution - 1)
        let pressure = 0.0
        for (let i = 0; i < nSources; i += 1) {
          const base = i * 4
          const sx = nodes[base]
          const sy = nodes[base + 1]
          const sz = nodes[base + 2]
          const amp = nodes[base + 3]
          const dx = x - sx
          const dy = y - sy
          const dz = zSliceVal - sz
          const r = Math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-6
          const phase = 6.28318530718 * freq * t - r / 340.0
          pressure += amp * Math.sin(phase)
        }
        return pressure
      })
      .setOutput([res, res])
      .setPipeline(false)
      .setPrecision('single')
    kernelRef.current = kernel
    return () => {
      kernel.destroy?.()
    }
  }, [res])

  useEffect(() => {
    setField(new Float32Array(res * res))
  }, [res])

  const nodesBuffer = useMemo(() => {
    const buf = new Float32Array(Math.max(1, acousticNodes.length) * 4)
    for (let i = 0; i < acousticNodes.length; i += 1) {
      const node = acousticNodes[i]
      buf[i * 4 + 0] = node.x
      buf[i * 4 + 1] = node.y
      buf[i * 4 + 2] = node.z
      buf[i * 4 + 3] = node.amp
    }
    return buf
  }, [acousticNodes])

  useFrame((state) => {
    const kernel = kernelRef.current
    if (!kernel) return
    const output = kernel(nodesBuffer, currentFreq, state.clock.elapsedTime, acousticNodes.length, zSlice, res) as number[][]
    const nextField = new Float32Array(res * res)
    let idx = 0
    for (let y = 0; y < res; y += 1) {
      const row = output[y]
      for (let x = 0; x < res; x += 1) {
        nextField[idx++] = row[x]
      }
    }
    setField(nextField)
  })

  const preset: QualityPreset = useMemo(() => qualityPresets[qualityKey], [qualityKey])

  return (
    <>
      <EffectComposer>
        {preset.postProcessing && <SSAO radius={0.2} intensity={20} />}
        <Bloom luminanceThreshold={0.85} intensity={0.2} />
      </EffectComposer>
      <EnclosureMesh geometry={geometry} />
      <PressureField data={field} res={res} />
      <PortFlowLines points={[[0, 0, 0], [1, 0, 0.1], [1, 1, 0.2]]} />
    </>
  )
}
