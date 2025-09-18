import { unpack } from 'msgpackr'
import { parseSolverMessage, type IterationMessage, type TopologySwitchMessage, type ConstraintViolationMessage, type ConvergenceMessage, type SolverMessage } from '@lib/protocol'

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

export type WSHandlers = {
  onIteration?: (data: IterationMessage) => void
  onTopology?: (data: TopologySwitchMessage) => void
  onViolation?: (data: ConstraintViolationMessage) => void
  onConvergence?: (data: ConvergenceMessage) => void
  onRawMessage?: (message: SolverMessage) => void
  onStatusChange?: (status: ConnectionStatus) => void
  onError?: (ev: Event) => void
}

export class SolverWS {
  private readonly url: string
  private ws: WebSocket | null = null
  private readonly handlers: WSHandlers
  private backoff = 1000
  private shouldReconnect = true
  private status: ConnectionStatus = 'idle'

  constructor(url: string, handlers: WSHandlers = {}) {
    this.url = url
    this.handlers = handlers
  }

  get connectionStatus(): ConnectionStatus {
    return this.status
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    this.shouldReconnect = true
    this.updateStatus(this.ws ? 'reconnecting' : 'connecting')

    this.ws = new WebSocket(this.url)
    this.ws.binaryType = 'arraybuffer'

    this.ws.onopen = () => {
      this.backoff = 1000
      this.updateStatus('open')
    }

    this.ws.onclose = () => {
      this.ws = null
      if (this.shouldReconnect) {
        this.updateStatus('reconnecting')
        setTimeout(() => this.reconnect(), this.backoff)
        this.backoff = Math.min(10000, this.backoff * 1.7)
      } else {
        this.updateStatus('closed')
      }
    }

    this.ws.onerror = (ev) => {
      this.handlers.onError?.(ev)
    }

    this.ws.onmessage = async (ev) => {
      const buf = ev.data instanceof ArrayBuffer ? ev.data : await (ev.data as Blob).arrayBuffer()
      const unpacked = unpack(new Uint8Array(buf))
      const message = parseSolverMessage(unpacked)
      if (!message) {
        return
      }
      this.handlers.onRawMessage?.(message)
      switch (message.type) {
        case 'ITERATION':
          this.handlers.onIteration?.(message.data)
          break
        case 'TOPOLOGY_SWITCH':
          this.handlers.onTopology?.(message)
          break
        case 'CONSTRAINT_VIOLATION':
          this.handlers.onViolation?.(message)
          break
        case 'CONVERGENCE':
          this.handlers.onConvergence?.(message.data)
          break
        default:
          break
      }
    }
  }

  send(payload: unknown) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return
    }
    this.ws.send(payload as any)
  }

  private reconnect() {
    if (!this.shouldReconnect) {
      return
    }
    this.connect()
  }

  close() {
    this.shouldReconnect = false
    if (this.ws) {
      this.ws.close()
    } else {
      this.updateStatus('closed')
    }
  }

  private updateStatus(status: ConnectionStatus) {
    if (this.status === status) return
    this.status = status
    this.handlers.onStatusChange?.(status)
  }
}
