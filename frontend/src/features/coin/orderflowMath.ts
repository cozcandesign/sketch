// Order flow panellerinin saf hesapları. Bileşen dosyalarından ayrıdır: hem test edilebilir
// kalsınlar hem de bileşen dosyaları yalnızca bileşen dışa aktarsın (eslint react-refresh).
import type { OrderflowPoint } from '@/api/types'

export const LIQUIDATION_BUCKET_MINUTES = 15
export const BOOK_AVERAGE_MINUTES = 5
/** Bu eşiğin altındaki emir defteri dengesizliği "dengeli" sayılır; altında yön okumak gürültüdür. */
export const BOOK_BALANCED = 0.05

export type OiState = 'realBuying' | 'shortBuilding' | 'shortCovering' | 'longUnwinding' | null

/**
 * Açık pozisyon ve fiyatın birlikte hareketi (ARCHITECTURE.md §8.3 dört durumu).
 * Yön ham değişimin işaretinden gelir; modülün skorunu değil, okunan durumu adlandırır.
 */
export function oiState(oiChange: number | null, priceChange: number | null): OiState {
  if (oiChange == null || priceChange == null) return null
  if (oiChange > 0) return priceChange > 0 ? 'realBuying' : 'shortBuilding'
  return priceChange > 0 ? 'shortCovering' : 'longUnwinding'
}

export interface LiquidationBucket {
  ts: string
  long: number
  short: number
}

/**
 * Dakika satırlarını 15 dakikalık kovalara toplar. Kovanın etiketi başlangıç anıdır;
 * veri gelmemiş dakikalar sıfır sayılır.
 */
export function bucketLiquidations(
  points: OrderflowPoint[],
  bucketMinutes = LIQUIDATION_BUCKET_MINUTES,
): LiquidationBucket[] {
  const size = bucketMinutes * 60_000
  const buckets = new Map<number, LiquidationBucket>()
  for (const point of points) {
    const start = Math.floor(new Date(point.ts).getTime() / size) * size
    const bucket = buckets.get(start) ?? { ts: new Date(start).toISOString(), long: 0, short: 0 }
    bucket.long += point.liq_long_usd ?? 0
    bucket.short += point.liq_short_usd ?? 0
    buckets.set(start, bucket)
  }
  return [...buckets.entries()].sort(([a], [b]) => a - b).map(([, bucket]) => bucket)
}

/** Son `minutes` dakikanın ortalaması; hiç değer yoksa `null` (sıfır değil: "veri yok" başka şey). */
export function recentAverage(
  points: OrderflowPoint[],
  key: 'top20_imbalance' | 'depth1pct_imbalance',
  minutes = BOOK_AVERAGE_MINUTES,
): number | null {
  const values = points
    .slice(-minutes)
    .map((point) => point[key])
    .filter((value): value is number => value != null)
  if (values.length === 0) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

/**
 * Pencere net akışının hacme oranı (ARCHITECTURE.md §8.3 `cvd` bileşeniyle aynı normalizasyon:
 * CVD hacim birimindedir, fiyatla ölçeklenmez). Hacim yoksa `null`.
 */
export function flowRatio(points: OrderflowPoint[]): number | null {
  let net = 0
  let volume = 0
  for (const point of points) {
    net += point.cvd_delta ?? 0
    volume += (point.buy_vol ?? 0) + (point.sell_vol ?? 0)
  }
  if (volume <= 0) return null
  return net / volume
}
