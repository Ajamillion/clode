import { Suspense, useMemo } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { EnclosureRenderer } from '@core/EnclosureRenderer'
import { OptimizationHUD } from '@components/OptimizationHUD'
import type { MeshData, AcousticNode } from '@types/index'

const demoMesh: MeshData = {
  vertices: new Float32Array([-0.3, 0, 0, 0.3, 0, 0, 0, 0.5, 0]),
  indices: new Uint32Array([0, 1, 2])
}

export default function App() {
  const nodes: AcousticNode[] = useMemo(
    () => [
      { x: 0.2, y: 0.2, z: 0.5, amp: 1.0 },
      { x: 0.7, y: 0.6, z: 0.5, amp: 0.7 }
    ],
    []
  )

  return (
    <div className="app-shell">
      <Suspense fallback={<div className="app-loading">Loading…</div>}>
        <Canvas camera={{ position: [0.8, 0.6, 1.2], fov: 50 }}>
          <ambientLight intensity={0.6} />
          <pointLight position={[3, 3, 3]} />
          <EnclosureRenderer geometry={demoMesh} acousticNodes={nodes} currentFreq={60} />
          <OrbitControls makeDefault />
        </Canvas>
      </Suspense>
      <OptimizationHUD />
    </div>
  )
}
