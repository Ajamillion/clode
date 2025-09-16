import http from 'http'
import { randomUUID } from 'crypto'
import { pack } from 'msgpackr'
import { WebSocketServer } from 'ws'

const runs = new Map()
const sockets = new Set()
const simulations = new Map()

function nowSeconds() {
  return Date.now() / 1000
}

function sendJson(res, status, payload) {
  res.writeHead(status, { 'content-type': 'application/json' })
  res.end(JSON.stringify(payload))
}

function buildResponseTraces(iter) {
  const points = 60
  const frequencies = Array.from({ length: points }, (_, i) => 20 * Math.pow(200 / 20, i / (points - 1)))
  const peak = 108 + Math.min(iter, 80) * 0.16
  const spl = frequencies.map((f) => peak - 12 * Math.exp(-(Math.log10(f) - Math.log10(55)) ** 2))
  const impedanceReal = frequencies.map((f, idx) => 5.2 + Math.sin(idx / 6) * 0.6)
  const impedanceImag = frequencies.map((_, idx) => Math.cos(idx / 8) * 0.9)
  const coneVelocity = frequencies.map((_, idx) => 0.25 + 0.04 * Math.sin(idx / 5))
  const coneDisp = coneVelocity.map((vel, idx) => vel / (2 * Math.PI * Math.max(frequencies[idx], 1)))
  const portVelocity = frequencies.map((f) => 8 + 2 * Math.exp(-(Math.log(f) - Math.log(40)) ** 2))
  return {
    frequency_hz: frequencies,
    spl_db: spl,
    impedance_real: impedanceReal,
    impedance_imag: impedanceImag,
    cone_velocity_ms: coneVelocity,
    cone_displacement_m: coneDisp,
    port_velocity_ms: portVelocity
  }
}

function buildSummary(traces) {
  const maxSpl = Math.max(...traces.spl_db)
  return {
    fb_hz: 42.0,
    f3_low_hz: 32.0,
    f3_high_hz: 205.0,
    max_spl_db: maxSpl,
    max_cone_velocity_ms: Math.max(...traces.cone_velocity_ms),
    max_cone_displacement_m: Math.max(...traces.cone_displacement_m),
    max_port_velocity_ms: Math.max(...traces.port_velocity_ms),
    excursion_ratio: 0.58,
    excursion_headroom_db: 10.8,
    safe_drive_voltage_v: 7.2
  }
}

function broadcast(message) {
  const payload = typeof message === 'string' ? message : pack(message)
  for (const socket of sockets) {
    if (socket.readyState === socket.OPEN) {
      socket.send(payload)
    }
  }
}

function updateRunHistory(run, entry) {
  if (!run.result) {
    run.result = { history: [] }
  }
  const history = run.result.history ?? []
  history.push(entry)
  run.result.history = history.slice(-256)
  run.updated_at = nowSeconds()
}

function startSimulation(run, params) {
  run.status = 'running'
  run.updated_at = nowSeconds()
  let iter = 0
  const timer = setInterval(() => {
    iter += 1
    const loss = Math.max(Math.exp(-iter / 55), 0.0015)
    const gradNorm = Math.max(loss / (iter + 4), 0.0008)
    const metrics = {
      spl: 110 + Math.min(iter, 80) * 0.18,
      spl_peak: 112 + Math.min(iter, 80) * 0.2,
      volume_l: Number(params.maxVolume ?? 60)
    }
    updateRunHistory(run, { iter, loss, gradNorm, metrics })

    broadcast({
      type: 'ITERATION',
      data: {
        iter,
        loss,
        gradNorm,
        topology: iter > 60 ? 'metamaterial' : 'baseline',
        timestamp: Date.now(),
        metrics
      }
    })

    if (iter === 45) {
      broadcast({ type: 'TOPOLOGY_SWITCH', from: 'baseline', to: 'metamaterial' })
    }

    if (iter % 30 === 0) {
      broadcast({
        type: 'CONSTRAINT_VIOLATION',
        constraint: 'port_velocity',
        severity: 0.35 + Math.random() * 0.2,
        location: { section: 'port', index: 1 }
      })
    }

    if (iter >= 90) {
      clearInterval(timer)
      simulations.delete(run.id)
      const traces = buildResponseTraces(iter)
      const summary = buildSummary(traces)
      run.status = 'succeeded'
      run.updated_at = nowSeconds()
      run.result = {
        history: run.result?.history ?? [],
        convergence: {
          converged: true,
          finalLoss: loss,
          iterations: iter,
          cpuTime: 14.2,
          solution: {
            alignment: params.preferAlignment === 'vented' ? 'vented' : 'sealed',
            fb_hz: summary.fb_hz,
            spl_peak: summary.max_spl_db,
            max_port_velocity_ms: summary.max_port_velocity_ms,
            safe_drive_voltage_v: summary.safe_drive_voltage_v
          }
        },
        summary,
        response: traces,
        metrics: {
          target_spl_db: Number(params.targetSpl ?? 118),
          achieved_spl_db: summary.max_spl_db,
          volume_l: Number(params.maxVolume ?? 60),
          safe_drive_voltage_v: summary.safe_drive_voltage_v,
          max_port_velocity_ms: summary.max_port_velocity_ms
        }
      }

      broadcast({
        type: 'CONVERGENCE',
        data: run.result.convergence
      })
    }
  }, 160)

  simulations.set(run.id, timer)
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost')

  if (req.method === 'POST' && url.pathname === '/api/opt/start') {
    let body = ''
    req.on('data', (chunk) => { body += chunk })
    req.on('end', () => {
      const params = body ? JSON.parse(body) : {}
      const now = nowSeconds()
      const id = randomUUID()
      const record = {
        id,
        status: 'queued',
        created_at: now,
        updated_at: now,
        params,
        result: null,
        error: null
      }
      runs.set(id, record)
      sendJson(res, 200, record)

      setTimeout(() => {
        const current = runs.get(id)
        if (!current) return
        startSimulation(current, params)
      }, 200)
    })
    return
  }

  if (req.method === 'GET' && url.pathname === '/api/opt/runs') {
    const limit = Number(url.searchParams.get('limit') ?? '20')
    const status = url.searchParams.get('status')
    let records = Array.from(runs.values())
    if (status) {
      records = records.filter((run) => run.status === status)
    }
    records.sort((a, b) => b.created_at - a.created_at)
    sendJson(res, 200, { runs: records.slice(0, Math.max(1, limit)) })
    return
  }

  if (req.method === 'GET' && url.pathname === '/api/opt/stats') {
    const counts = { queued: 0, running: 0, succeeded: 0, failed: 0 }
    for (const run of runs.values()) {
      counts[run.status] += 1
    }
    const total = Object.values(counts).reduce((sum, value) => sum + value, 0)
    sendJson(res, 200, { counts, total })
    return
  }

  if (req.method === 'GET' && url.pathname.startsWith('/api/opt/')) {
    const id = url.pathname.split('/').pop()
    if (!id || !runs.has(id)) {
      sendJson(res, 404, { error: 'not found' })
      return
    }
    sendJson(res, 200, runs.get(id))
    return
  }

  res.writeHead(200)
  res.end('OK')
})

const wss = new WebSocketServer({ noServer: true })

wss.on('connection', (ws) => {
  sockets.add(ws)
  ws.on('close', () => {
    sockets.delete(ws)
  })
})

server.on('upgrade', (req, socket, head) => {
  if (req.url === '/ws') {
    wss.handleUpgrade(req, socket, head, (ws) => {
      wss.emit('connection', ws, req)
    })
  } else {
    socket.destroy()
  }
})

server.listen(8787, () => {
  console.log('Mock API+WS on http://localhost:8787 (WS at /ws)')
})
