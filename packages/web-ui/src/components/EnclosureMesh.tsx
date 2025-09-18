import { useMemo } from 'react'
import * as THREE from 'three'
import type { MeshData } from '@types/index'

export function EnclosureMesh({ geometry }: { geometry: MeshData }) {
  const meshGeometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(geometry.vertices, 3))
    g.setIndex(new THREE.BufferAttribute(geometry.indices, 1))
    g.computeVertexNormals()
    return g
  }, [geometry])

  return (
    <mesh geometry={meshGeometry}>
      <meshStandardMaterial metalness={0.1} roughness={0.8} color="#9aa3af" />
    </mesh>
  )
}
