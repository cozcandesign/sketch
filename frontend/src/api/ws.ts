// Tek WebSocket istemcisi (ARCHITECTURE.md §15): otomatik yeniden bağlanma, abonelik seti.
// Bileşenler bunu doğrudan kullanmaz; useLive hook'u mesajları query cache'ine aktarır.

export type WsStatus = 'connecting' | 'connected' | 'disconnected'

export type WsInbound =
  | { op: 'hello'; api_version: string; server_time: string }
  | { op: 'pong'; server_time: string }
  | { op: 'subscribed'; topics: string[] }
  | { op: 'error'; message: string }
  | { topic: string; ts: string; data: unknown }

export function isTopicMessage(
  msg: WsInbound,
): msg is { topic: string; ts: string; data: unknown } {
  return 'topic' in msg
}

type MessageListener = (msg: WsInbound) => void
type StatusListener = (status: WsStatus) => void

const RECONNECT_BASE_MS = 1_000
const RECONNECT_CAP_MS = 30_000

export function defaultWsUrl(loc: Location = window.location): string {
  const proto = loc.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${loc.host}/ws`
}

export class WsClient {
  private socket: WebSocket | null = null
  private topics = new Set<string>()
  private messageListeners = new Set<MessageListener>()
  private statusListeners = new Set<StatusListener>()
  private attempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private closedByUser = false
  private _status: WsStatus = 'disconnected'
  lastMessageAt: Date | null = null

  constructor(private readonly url: string) {}

  get status(): WsStatus {
    return this._status
  }

  connect(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return
    this.closedByUser = false
    this.setStatus('connecting')
    const socket = new WebSocket(this.url)
    this.socket = socket
    socket.onopen = () => {
      this.attempt = 0
      this.setStatus('connected')
      if (this.topics.size > 0) this.send({ op: 'subscribe', topics: [...this.topics] })
    }
    socket.onmessage = (event: MessageEvent<string>) => {
      let parsed: WsInbound
      try {
        parsed = JSON.parse(event.data) as WsInbound
      } catch {
        return
      }
      this.lastMessageAt = new Date()
      for (const listener of this.messageListeners) listener(parsed)
    }
    socket.onclose = () => {
      this.socket = null
      this.setStatus('disconnected')
      if (!this.closedByUser) this.scheduleReconnect()
    }
    socket.onerror = () => {
      // onclose arkasından gelir; yeniden bağlanma orada planlanır
    }
  }

  close(): void {
    this.closedByUser = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this.socket?.close()
    this.socket = null
    this.setStatus('disconnected')
  }

  subscribe(topics: string[]): void {
    for (const t of topics) this.topics.add(t)
    if (this._status === 'connected') this.send({ op: 'subscribe', topics })
  }

  unsubscribe(topics: string[]): void {
    for (const t of topics) this.topics.delete(t)
    if (this._status === 'connected') this.send({ op: 'unsubscribe', topics })
  }

  ping(): void {
    if (this._status === 'connected') this.send({ op: 'ping' })
  }

  onMessage(listener: MessageListener): () => void {
    this.messageListeners.add(listener)
    return () => this.messageListeners.delete(listener)
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener)
    listener(this._status)
    return () => this.statusListeners.delete(listener)
  }

  /** Bir sonraki yeniden bağlanma gecikmesi (ms): 1s, 2s, 4s ... en fazla 30s. */
  nextDelayMs(): number {
    return Math.min(RECONNECT_CAP_MS, RECONNECT_BASE_MS * 2 ** this.attempt)
  }

  private scheduleReconnect(): void {
    const delay = this.nextDelayMs()
    this.attempt += 1
    this.reconnectTimer = setTimeout(() => this.connect(), delay)
  }

  private send(payload: Record<string, unknown>): void {
    this.socket?.send(JSON.stringify(payload))
  }

  private setStatus(status: WsStatus): void {
    if (this._status === status) return
    this._status = status
    for (const listener of this.statusListeners) listener(status)
  }
}

let singleton: WsClient | null = null

export function getWsClient(): WsClient {
  singleton ??= new WsClient(defaultWsUrl())
  return singleton
}
