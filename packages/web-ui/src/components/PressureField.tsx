import { useMemo } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'

export function PressureField({ data, res }: { data: Float32Array; res: number }) {
  const texture = useMemo(() => {
    const normalized = new Float32Array(data.length)
    let min = Infinity
    let max = -Infinity

    for (let i = 0; i < data.length; i += 1) {
      const value = data[i]
      if (value < min) min = value
      if (value > max) max = value
    }

    const range = max - min || 1
    for (let i = 0; i < data.length; i += 1) {
      normalized[i] = (data[i] - min) / range
    }

    const tex = new THREE.DataTexture(normalized, res, res, THREE.RedFormat, THREE.FloatType)
    tex.needsUpdate = true
    tex.colorSpace = THREE.LinearSRGBColorSpace
    return tex
  }, [data, res])

  useFrame(() => {
    texture.needsUpdate = true
  })

  return (
    <mesh position={[0.5, 0.5, 0.001]}>
      <planeGeometry args={[1, 1, 1, 1]} />
      <shaderMaterial uniforms={{ uTex: { value: texture } }} vertexShader={vertexShader} fragmentShader={fragmentShader} transparent />
    </mesh>
  )
}

const vertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const fragmentShader = /* glsl */ `
  precision highp float;
  uniform sampler2D uTex;
  varying vec2 vUv;

  vec3 turbo(float x){
    return clamp(vec3(
      34.61 + x*(1172.33 + x*(-10743.0 + x*(33300.0 + x*(-38394.0 + x*15417.0)))) ,
      23.31 + x*(557.33 + x*(1225.0 + x*(-3574.0 + x*(4107.0 + x*(-1625.0))))) ,
      27.2 + x*(321.0 + x*(1844.0 + x*(-3544.0 + x*(2752.0 + x*(-780.0)))))
    )/255.0,0.0,1.0);
  }

  void main(){
    float v = texture2D(uTex, vUv).r;
    vec3 col = turbo(v);
    gl_FragColor = vec4(col, 0.55);
  }
`
