import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { OrderflowSection } from '@/features/coin/OrderflowSection'
import { mockApi, orderflow } from '@/test/mockApi'
import type { Orderflow } from '@/api/types'

afterEach(() => vi.unstubAllGlobals())

function renderSection(data: Orderflow) {
  mockApi({ '/orderflow': data })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <OrderflowSection symbol="BTCUSDT" priceChange24h={0.01} />
    </QueryClientProvider>,
  )
}

describe('OrderflowSection', () => {
  it('veri hiç yoksa panel uydurmaz, durumu söyler', async () => {
    renderSection({
      symbol: 'BTCUSDT',
      minutes: [],
      liquidations: [],
      funding: {
        last_rate: null,
        next_funding_time: null,
        mark_price: null,
        average_30d: null,
        zscore: null,
      },
      open_interest: { latest: null, latest_usd: null, ts: null, change_24h: null },
      long_short: [],
      coverage_ratio: 0,
    })

    expect(await screen.findByText(/order flow verisi yok/)).toBeInTheDocument()
    expect(screen.queryByText('Funding')).not.toBeInTheDocument()
  })

  it('kapsama düşükse uyarı gösterir: eksik veriyle hesaplandığı gizlenmez', async () => {
    renderSection({ ...orderflow, coverage_ratio: 0.42 })

    expect(await screen.findByText(/dinlenen süre %42/)).toBeInTheDocument()
    expect(screen.getByText(/eksik veriyle hesaplanmıştır/)).toBeInTheDocument()
  })

  it('kapsama tamsa uyarı çıkmaz', async () => {
    renderSection(orderflow)

    expect(await screen.findByText('Funding')).toBeInTheDocument()
    expect(screen.queryByText(/eksik veriyle hesaplanmıştır/)).not.toBeInTheDocument()
  })
})
