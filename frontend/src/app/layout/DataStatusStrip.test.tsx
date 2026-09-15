import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { Providers } from '@/app/providers'
import { DataStatusStrip } from '@/app/layout/DataStatusStrip'
import type { HealthResponse } from '@/api/types'

const health: HealthResponse = {
  status: 'degraded',
  server_time: '2026-01-01T12:00:00Z',
  api_version: '0.1.0',
  engine: {
    alive: true,
    last_heartbeat: '2026-01-01T11:59:50Z',
    age_seconds: 10,
    version: '0.1.0',
  },
  collectors: [
    {
      collector: 'rss',
      status: 'degraded',
      last_success_at: '2026-01-01T11:40:00Z',
      last_error_at: '2026-01-01T11:59:00Z',
      last_error: 'timeout',
      consecutive_failures: 2,
    },
    {
      collector: 'spot_klines',
      status: 'ok',
      last_success_at: '2026-01-01T11:59:55Z',
      last_error_at: null,
      last_error: null,
      consecutive_failures: 0,
    },
  ],
  db: { size_bytes: 4096 },
  outbox: { last_id: 3, last_event_at: null, lag_seconds: null },
  ws: { clients: 1 },
  live_prices: {
    connected: true,
    last_message_at: '2026-01-01T11:59:59Z',
    messages: 42,
    reconnects: 0,
  },
}

function mockFetch(body: unknown, ok = true) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok,
      status: ok ? 200 : 500,
      statusText: ok ? 'OK' : 'ERR',
      json: async () => body,
      text: async () => JSON.stringify(body),
    })),
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('DataStatusStrip', () => {
  it('renders engine state and one cell per collector', async () => {
    mockFetch(health)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <Providers live={false} client={client}>
        <DataStatusStrip />
      </Providers>,
    )
    expect(await screen.findByText('rss')).toBeInTheDocument()
    expect(screen.getByText('spot_klines')).toBeInTheDocument()
    expect(screen.getByText('aksıyor')).toBeInTheDocument()
    expect(screen.getByText('çalışıyor')).toBeInTheDocument()
    expect(screen.getByText('engine çalışıyor')).toBeInTheDocument()
  })

  it('shows the empty note when there are no collectors yet', async () => {
    mockFetch({ ...health, collectors: [], status: 'ok' })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <Providers live={false} client={client}>
        <DataStatusStrip />
      </Providers>,
    )
    expect(await screen.findByText(/Henüz collector yok/)).toBeInTheDocument()
  })
})
