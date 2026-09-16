// Üretilen OpenAPI tiplerine kısa adlar. types.gen.ts elle düzenlenmez (`npm run gen-types`).
import type { components } from '@/api/types.gen'

export type HealthResponse = components['schemas']['HealthResponse']
export type CollectorHealth = components['schemas']['CollectorHealthOut']
export type HealthStatus = CollectorHealth['status']

export type MarketState = components['schemas']['MarketStateOut']
export type HorizonState = components['schemas']['HorizonStateOut']
export type Prediction = components['schemas']['PredictionOut']
export type PredictionPage = components['schemas']['PredictionPage']
export type Outcome = components['schemas']['OutcomeOut']
export type ConfidenceLabel = Prediction['confidence_label']
export type Calibration = components['schemas']['CalibrationOut']
export type CalibrationBin = components['schemas']['CalibrationBinOut']
export type ModelSummary = components['schemas']['ModelSummaryOut']
export type HorizonSummary = components['schemas']['HorizonSummaryOut']
export type ModuleSummary = components['schemas']['ModuleSummaryOut']
export type SymbolsResponse = components['schemas']['SymbolsOut']
export type Candles = components['schemas']['CandlesOut']
export type Candle = components['schemas']['CandleOut']
export type Signals = components['schemas']['SignalsOut']
export type HorizonSignals = components['schemas']['HorizonSignalsOut']
export type ModuleSignal = components['schemas']['SignalOut']
export type Levels = components['schemas']['LevelsOut']
export type Level = components['schemas']['LevelOut']
export type VolumeProfile = components['schemas']['VolumeProfileOut']

/** WebSocket `price.{symbol}` yükü (şemadan üretilmez: WS tipleri OpenAPI'de yok). */
export interface LivePrice {
  price: number | null
  change24h?: number | null
  high24h?: number
  low24h?: number
  ts?: string
  stale: boolean
}

/** Mum grafiğinde seçilebilen zaman dilimleri. */
export const CHART_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d'] as const
export type IntervalKey = (typeof CHART_INTERVALS)[number]

export const HORIZONS = ['30m', '1h', '4h', '24h'] as const
export type HorizonKey = (typeof HORIZONS)[number]

export const HORIZON_LABELS: Record<HorizonKey, string> = {
  '30m': '30 dk',
  '1h': '1 saat',
  '4h': '4 saat',
  '24h': '24 saat',
}
