import { describe, expect, it } from 'vitest'
import { WsClient, defaultWsUrl, isTopicMessage } from '@/api/ws'

describe('ws helpers', () => {
  it('builds ws url from location', () => {
    expect(defaultWsUrl({ protocol: 'http:', host: 'localhost:3000' } as Location)).toBe(
      'ws://localhost:3000/ws',
    )
    expect(defaultWsUrl({ protocol: 'https:', host: 'mp.local' } as Location)).toBe(
      'wss://mp.local/ws',
    )
  })
  it('distinguishes topic messages from ops', () => {
    expect(isTopicMessage({ op: 'pong', server_time: 'x' })).toBe(false)
    expect(isTopicMessage({ topic: 'health', ts: 'x', data: {} })).toBe(true)
  })
  it('reconnect delay doubles up to 30s', () => {
    const client = new WsClient('ws://example/ws')
    expect(client.nextDelayMs()).toBe(1_000)
    expect(client.status).toBe('disconnected')
  })
})
