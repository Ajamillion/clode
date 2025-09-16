import http from 'http'
import { pack } from 'msgpackr'
import { WebSocketServer } from 'ws'

const server = http.createServer((req, res) => {
  if (req.url === '/api/opt/start' && req.method === 'POST') {
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ status: 'ok' }))
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
