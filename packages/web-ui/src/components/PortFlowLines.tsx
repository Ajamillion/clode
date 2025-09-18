import { Line } from '@react-three/drei'

export function PortFlowLines({ points }: { points?: [number, number, number][] }) {
  if (!points || points.length < 2) return null
  return <Line points={points} lineWidth={1} color="#10b981" dashed />
}
