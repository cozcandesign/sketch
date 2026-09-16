import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LiquidationPanel } from '@/features/coin/LiquidationPanel'
import { OIPanel } from '@/features/coin/OIPanel'
import { OrderBookPanel } from '@/features/coin/OrderBookPanel'
import { FundingPanel } from '@/features/coin/FundingPanel'
import {
  bucketLiquidations,
  flowRatio,
  oiState,
  recentAverage,
} from '@/features/coin/orderflowMath'
import type { OrderflowPoint } from '@/api/types'

function point(overrides: Partial<OrderflowPoint> & { ts: string }): OrderflowPoint {
  return {
    buy_vol: 0,
    sell_vol: 0,
    cvd_delta: 0,
    cvd_cumulative: 0,
    trade_count: 0,
    liq_long_usd: 0,
    liq_short_usd: 0,
    top20_imbalance: null,
    depth1pct_imbalance: null,
    spread_bps: null,
    coverage_seconds: 60,
    ...overrides,
  }
}

describe('oiState', () => {
  it('adlandırır: açık pozisyon ve fiyatın dört bileşimi', () => {
    expect(oiState(0.02, 0.01)).toBe('realBuying')
    expect(oiState(0.02, -0.01)).toBe('shortBuilding')
    expect(oiState(-0.02, 0.01)).toBe('shortCovering')
    expect(oiState(-0.02, -0.01)).toBe('longUnwinding')
  })

  it('veri eksikse durum üretmez', () => {
    expect(oiState(null, 0.01)).toBeNull()
    expect(oiState(0.02, null)).toBeNull()
  })
})

describe('bucketLiquidations', () => {
  it('dakikaları 15 dakikalık kovalara toplar', () => {
    const buckets = bucketLiquidations([
      point({ ts: '2026-01-01T10:01:00Z', liq_long_usd: 100 }),
      point({ ts: '2026-01-01T10:14:00Z', liq_long_usd: 50 }),
      point({ ts: '2026-01-01T10:16:00Z', liq_short_usd: 70 }),
    ])
    expect(buckets).toHaveLength(2)
    expect(buckets[0]).toMatchObject({ long: 150, short: 0 })
    expect(buckets[1]).toMatchObject({ long: 0, short: 70 })
  })

  it('kovaları zamana göre sıralar', () => {
    const buckets = bucketLiquidations([
      point({ ts: '2026-01-01T11:00:00Z', liq_long_usd: 10 }),
      point({ ts: '2026-01-01T10:00:00Z', liq_long_usd: 20 }),
    ])
    expect(buckets.map((bucket) => bucket.long)).toEqual([20, 10])
  })
})

describe('recentAverage', () => {
  it('son dakikaların ortalamasını alır', () => {
    const points = [
      point({ ts: '2026-01-01T10:00:00Z', top20_imbalance: 1 }),
      point({ ts: '2026-01-01T10:01:00Z', top20_imbalance: 0.5 }),
    ]
    expect(recentAverage(points, 'top20_imbalance', 2)).toBeCloseTo(0.75)
  })

  it('hiç değer yoksa sıfır değil null döner', () => {
    const points = [point({ ts: '2026-01-01T10:00:00Z' })]
    expect(recentAverage(points, 'depth1pct_imbalance')).toBeNull()
  })
})

describe('flowRatio', () => {
  it('net akışı pencerenin hacmine oranlar', () => {
    const points = [
      point({ ts: '2026-01-01T10:00:00Z', cvd_delta: 6, buy_vol: 30, sell_vol: 24 }),
      point({ ts: '2026-01-01T10:01:00Z', cvd_delta: -2, buy_vol: 20, sell_vol: 22 }),
    ]
    expect(flowRatio(points)).toBeCloseTo(4 / 96)
  })

  it('hacim yoksa oran hesaplamaz', () => {
    expect(flowRatio([])).toBeNull()
  })
})

describe('paneller', () => {
  it('funding kalabalığını ve long/short oranlarını yazar', () => {
    render(
      <FundingPanel
        funding={{
          last_rate: 0.00021,
          next_funding_time: null,
          mark_price: null,
          average_30d: 0.00008,
          zscore: 1.8,
        }}
        longShort={[
          {
            kind: 'global_account',
            long_ratio: 0.55,
            short_ratio: 0.45,
            ratio: 1.22,
            ts: '2026-01-01T11:55:00Z',
          },
        ]}
      />,
    )
    expect(screen.getByText('long tarafı kalabalık')).toBeInTheDocument()
    expect(screen.getByText('tüm hesaplar')).toBeInTheDocument()
    expect(screen.getByText('1,22')).toBeInTheDocument()
  })

  it('açık pozisyonu sözleşme ve USD olarak ayrı gösterir', () => {
    render(
      <OIPanel
        openInterest={{
          latest: 82_140,
          latest_usd: 5_174_820_000,
          ts: '2026-01-01T11:55:00Z',
          change_24h: 0.031,
        }}
        priceChange24h={0.012}
      />,
    )
    expect(screen.getByText('yeni pozisyon girişi')).toBeInTheDocument()
    expect(screen.getByText(/5,17 Mr \$/)).toBeInTheDocument()
  })

  it('zorunlu kapatma yoksa bunu söyler', () => {
    render(<LiquidationPanel points={[point({ ts: '2026-01-01T10:00:00Z' })]} />)
    expect(screen.getByText(/zorunlu kapatma yok/)).toBeInTheDocument()
  })

  it('emir defteri verisi yoksa yön uydurmaz', () => {
    render(<OrderBookPanel points={[point({ ts: '2026-01-01T10:00:00Z' })]} />)
    expect(screen.getByText('dengeli')).toBeInTheDocument()
  })
})
