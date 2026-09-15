import { vi } from 'vitest'
import type { Calibration, HealthResponse, MarketState, PredictionPage } from '@/api/types'

/** URL parçasına göre yanıt döndüren sahte fetch. Testlerde ağ yok. */
export function mockApi(routes: Record<string, unknown>): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const match = Object.keys(routes).find((key) => url.includes(key))
      if (!match) {
        return {
          ok: false,
          status: 404,
          statusText: 'not found',
          json: async () => ({}),
          text: async () => url,
        }
      }
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => routes[match],
        text: async () => JSON.stringify(routes[match]),
      }
    }),
  )
}

export const health: HealthResponse = {
  status: 'ok',
  server_time: '2026-01-01T12:00:00Z',
  api_version: '0.1.0',
  engine: { alive: true, last_heartbeat: '2026-01-01T11:59:55Z', age_seconds: 5, version: '0.1.0' },
  collectors: [
    {
      collector: 'spot_klines',
      status: 'ok',
      last_success_at: '2026-01-01T11:59:50Z',
      last_error_at: null,
      last_error: null,
      consecutive_failures: 0,
    },
  ],
  db: { size_bytes: 8192 },
  outbox: { last_id: 5, last_event_at: null, lag_seconds: null },
  ws: { clients: 1 },
  live_prices: {
    connected: true,
    last_message_at: '2026-01-01T11:59:59Z',
    messages: 10,
    reconnects: 0,
  },
  build: { git_sha: 'abc1234', started_at: '2026-01-01T11:00:00Z' },
}

export const marketState: MarketState = {
  symbol: 'BTCUSDT',
  price: { last: 63_000, change_24h: 0.05, as_of: '2026-01-01T12:00:00Z', stale: false },
  coverage: [{ interval: '1m', count: 1440, last_close_time: '2026-01-01T12:00:00Z' }],
  horizons: [
    {
      horizon: '30m',
      label_tr: '30 dakika',
      predictions: [
        {
          id: 1,
          symbol: 'BTCUSDT',
          horizon: '30m',
          as_of: '2026-01-01T11:45:00Z',
          target_at: '2026-01-01T12:15:00Z',
          price_at: 62_500,
          p_up: 0.62,
          expected_low: null,
          expected_high: null,
          confidence: 0.2,
          confidence_label: 'low',
          conflict: false,
          veto_active: false,
          veto_reason: null,
          source: 'baseline',
          model_version: 'baseline-climatology-1',
          non_overlapping: true,
          report: null,
          outcome: null,
        },
      ],
    },
    { horizon: '1h', label_tr: '1 saat', predictions: [] },
    { horizon: '4h', label_tr: '4 saat', predictions: [] },
    { horizon: '24h', label_tr: '24 saat', predictions: [] },
  ],
}

export const predictionPage: PredictionPage = {
  items: [
    {
      id: 2,
      symbol: 'BTCUSDT',
      horizon: '1h',
      as_of: '2026-01-01T10:00:00Z',
      target_at: '2026-01-01T11:00:00Z',
      price_at: 60_000,
      p_up: 0.7,
      expected_low: null,
      expected_high: null,
      confidence: 0.2,
      confidence_label: 'low',
      conflict: false,
      veto_active: false,
      veto_reason: null,
      source: 'baseline',
      model_version: 'baseline-climatology-1',
      non_overlapping: true,
      report: {
        headline: 'referans tahmin',
        reasons: [{ module: 'baseline', text: 'geçmiş oran' }],
      },
      outcome: {
        resolved_at: '2026-01-01T11:00:00Z',
        price_at_target: 61_000,
        realized_return: 0.0167,
        outcome: 'up',
        hit: true,
        brier: 0.09,
        resolved_by: 'ws',
      },
    },
  ],
  next_cursor: null,
}

export const calibration: Calibration = {
  subset: 'all',
  window_days: 30,
  overall: {
    n: 12,
    brier: 0.18,
    brier_skill: 0.28,
    base_rate: 0.5,
    hit_rate: 0.75,
    hit_ci_low: 0.47,
    hit_ci_high: 0.91,
    beats_uninformed: true,
  },
  by_model: [
    {
      model_version: 'baseline-climatology-1',
      label_tr: 'Referans: taban oranı',
      n: 6,
      brier: 0.2,
      brier_skill: 0.2,
      base_rate: 0.5,
      hit_rate: 0.66,
      hit_ci_low: 0.3,
      hit_ci_high: 0.9,
      beats_uninformed: true,
    },
  ],
  by_horizon: [
    {
      horizon: '1h',
      label_tr: '1 saat',
      n: 12,
      brier: 0.18,
      brier_skill: 0.28,
      base_rate: 0.5,
      hit_rate: 0.75,
      hit_ci_low: 0.47,
      hit_ci_high: 0.91,
      beats_uninformed: true,
    },
  ],
  bins: Array.from({ length: 10 }, (_, index) => ({
    bin: index,
    lower: index / 10,
    upper: (index + 1) / 10,
    n: index === 6 ? 12 : 0,
    mean_p: index === 6 ? 0.65 : null,
    observed_freq: index === 6 ? 0.7 : null,
  })),
  daily: [
    { day: '2026-01-01', n: 6, brier: 0.2, hit_rate: 0.66 },
    { day: '2026-01-02', n: 6, brier: 0.16, hit_rate: 0.83 },
  ],
  pending: 3,
}
