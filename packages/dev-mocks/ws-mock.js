import http from 'http'
import { pack } from 'msgpackr'
import { WebSocketServer } from 'ws'

const runs = new Map()

function sendJson(res, status, payload) {
  res.writeHead(status, { 'content-type': 'application/json' })
  res.end(JSON.stringify(payload))
}

function buildMockResult(params = {}) {
  const targetSpl = Number(params.targetSpl ?? 118)
  const volume = Number(params.maxVolume ?? 60)
  const history = []
  let loss = 1.2 + Math.max(0, (targetSpl - 110) / 12)
  for (let i = 1; i <= 14; i += 1) {
    loss = Math.max(loss * 0.74, 0.02)
    history.push({ iter: i, loss, gradNorm: Math.max(loss / (i + 2), 0.01) })
  }
  const finalLoss = history[history.length - 1]?.loss ?? 0.02
  const frequencies = Array.from({ length: 60 }, (_, i) => 20 * Math.pow(200 / 20, i / 59))
  const spl = frequencies.map((f) => 105 + 8 * Math.exp(-(Math.log(f) - Math.log(55)) ** 2))

  return {
    history,
    convergence: {
      converged: finalLoss < 0.1,
      finalLoss,
      iterations: history.length,
      solution: {
        spl_peak: Math.max(...spl),
        fc_hz: 46.5,
        qtc: 0.68,
        excursion_headroom_db: 9.8,
        safe_drive_voltage_v: 7.5
      }
    },
    summary: {
      fc_hz: 46.5,
      qtc: 0.68,
      f3_low_hz: 33.2,
      f3_high_hz: 210.0,
      max_spl_db: Math.max(...spl),
      max_cone_velocity_ms: 0.42,
      max_cone_displacement_m: 0.008,
      excursion_ratio: 0.62,
      excursion_headroom_db: 9.8,
      safe_drive_voltage_v: 7.5
    },
    response: {
      frequency_hz: frequencies,
      spl_db: spl,
      impedance_real: frequencies.map(() => 5 + Math.random()),
      impedance_imag: frequencies.map(() => Math.sin(Math.random())),
      cone_velocity_ms: frequencies.map(() => 0.2 + Math.random() * 0.1),
      cone_displacement_m: frequencies.map(() => 0.002 + Math.random() * 0.001)
    },
    metrics: {
      target_spl_db: targetSpl,
      achieved_spl_db: Math.max(...spl),
      volume_l: volume,
      safe_drive_voltage_v: 7.5
    }
  }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost')

  if (req.method === 'POST' && url.pathname === '/api/opt/start') {
    let body = ''
    req.on('data', (chunk) => { body += chunk })
    req.on('end', () => {
      const params = body ? JSON.parse(body) : {}
      const now = Date.now() / 1000
      const id = `${now.toString(16)}-${Math.random().toString(16).slice(2, 8)}`
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
        const running = { ...record, status: 'running', updated_at: Date.now() / 1000 }
        runs.set(id, running)
      }, 150)

      setTimeout(() => {
        const succeeded = {
          ...runs.get(id),
          status: 'succeeded',
          updated_at: Date.now() / 1000,
          result: buildMockResult(params)
        }
        runs.set(id, succeeded)
      }, 900)
    })
    return
  }

  if (req.method === 'GET' && url.pathname === '/api/opt/runs') {
    const limit = Number(url.searchParams.get('limit') ?? '20')
    const records = Array.from(runs.values())
      .sort((a, b) => b.created_at - a.created_at)
      .slice(0, Math.max(1, limit))
    sendJson(res, 200, { runs: records })
    return
  }

  if (req.method === 'GET' && url.pathname.startsWith('/api/opt/')) {
    const id = url.pathname.split('/').pop()
    if (!id) {
      sendJson(res, 400, { error: 'missing id' })
      return
    }
    const record = runs.get(id)
    if (!record) {
      sendJson(res, 404, { error: 'not found' })
      return
    }
    sendJson(res, 200, record)
    return
  }

  res.writeHead(200)
  res.end('OK')
})

const wss = new WebSocketServer({ noServer: true })

wss.on('connection', (ws) => {
  let iter = 0
  const timer = setInterval(() => {
    iter += 1
    const message = pack({
      type: 'ITERATION',
      data: {
        iter,
        loss: Math.exp(-iter / 55),
        gradNorm: 1 / (iter + 4),
        topology: iter > 50 ? 'metamaterial' : 'baseline',
        timestamp: Date.now(),
        metrics: {
          spl: 112 + Math.min(iter, 80) * 0.12,
          spl_peak: 114 + Math.min(iter, 80) * 0.15
        }
      }
    })
    ws.send(message)

    if (iter === 50) {
      ws.send(pack({ type: 'TOPOLOGY_SWITCH', from: 'baseline', to: 'metamaterial' }))
    }

    if (iter % 45 === 0) {
      ws.send(
        pack({
          type: 'CONSTRAINT_VIOLATION',
          constraint: 'port_velocity',
          severity: 0.4 + Math.random() * 0.1,
          location: { section: 'port', index: 2 }
        })
      )
    }

    if (iter === 90) {
      ws.send(
        pack({
          type: 'CONVERGENCE',
          data: {
            converged: true,
            finalLoss: Math.exp(-iter / 55),
            iterations: iter,
            cpuTime: 12.4,
            solution: { volume: 61.2, tuning: 38.5 }
          }
        })
      )
      clearInterval(timer)
    }
  }, 150)

  ws.on('close', () => clearInterval(timer))
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
