import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type CandlestickData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Candle, Level, VolumeProfile } from '@/api/types'

export interface PredictionMarker {
  time: number
  pUp: number
  hit: boolean | null
}

export interface CandleChartProps {
  candles: Candle[]
  levels?: Level[]
  profile?: VolumeProfile | null
  markers?: PredictionMarker[]
  showEma?: boolean
  showLevels?: boolean
  showProfile?: boolean
  height?: number
  ariaLabel: string
}

const EMA_PERIOD = 20
/** Grafikte yalnızca fiyata bu kadar ATR yakın seviyeler çizilir; gerisi tabloda kalır. */
const CHART_LEVEL_ATR = 3

/**
 * Mum grafiği. Renk yalnızca anlam taşır: yeşil/kırmızı mum yönü, seviye çizgileri gri,
 * tahmin işaretçileri sonuç rengiyle (isabet / ıska / bekliyor).
 *
 * Tüm renkler `tokens.css` değişkenlerinden okunur; burada hex yazılmaz (CLAUDE.md §7).
 */
export function CandleChart({
  candles,
  levels = [],
  profile = null,
  markers = [],
  showEma = true,
  showLevels = true,
  showProfile = true,
  height = 360,
  ariaLabel,
}: CandleChartProps) {
  const container = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const candleSeries = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const emaSeries = useRef<ISeriesApi<'Line'> | null>(null)
  const priceLines = useRef<IPriceLine[]>([])
  const markerPlugin = useRef<ISeriesMarkersPluginApi<Time> | null>(null)

  useEffect(() => {
    const element = container.current
    if (!element) return
    const styles = getComputedStyle(element)
    const token = (name: string) => styles.getPropertyValue(name).trim()

    const instance = createChart(element, {
      height,
      layout: {
        background: { color: 'transparent' },
        textColor: token('--color-muted'),
        fontFamily: token('--font-mono'),
        fontSize: 11,
      },
      grid: {
        vertLines: { color: token('--color-grid') },
        horzLines: { color: token('--color-grid') },
      },
      rightPriceScale: { borderColor: token('--color-border') },
      timeScale: { borderColor: token('--color-border'), timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
      handleScale: { axisPressedMouseMove: false },
    })
    chart.current = instance
    candleSeries.current = instance.addSeries(CandlestickSeries, {
      upColor: token('--color-up'),
      downColor: token('--color-down'),
      borderVisible: false,
      wickUpColor: token('--color-up'),
      wickDownColor: token('--color-down'),
    })
    emaSeries.current = instance.addSeries(LineSeries, {
      color: token('--color-series-1'),
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    })

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) instance.applyOptions({ width: entry.contentRect.width })
    })
    observer.observe(element)
    instance.applyOptions({ width: element.clientWidth })

    markerPlugin.current = createSeriesMarkers(candleSeries.current, [])

    return () => {
      observer.disconnect()
      instance.remove()
      chart.current = null
      candleSeries.current = null
      emaSeries.current = null
      markerPlugin.current = null
      priceLines.current = []
    }
  }, [height])

  useEffect(() => {
    const series = candleSeries.current
    if (!series) return
    series.setData(candles.map(toCandlestick))
    const ema = emaSeries.current
    if (ema) ema.setData(showEma ? emaLine(candles, EMA_PERIOD) : [])
    chart.current?.timeScale().fitContent()
  }, [candles, showEma])

  useEffect(() => {
    const series = candleSeries.current
    if (!series) return
    const element = container.current
    const token = (name: string) =>
      element ? getComputedStyle(element).getPropertyValue(name).trim() : ''
    for (const line of priceLines.current) series.removePriceLine(line)
    priceLines.current = []
    if (showLevels) {
      for (const level of levels.filter((item) => (item.distance_atr ?? 0) <= CHART_LEVEL_ATR)) {
        priceLines.current.push(
          series.createPriceLine({
            price: level.price,
            color: token('--color-neutral'),
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: `${level.touches}×`,
          }),
        )
      }
    }
    if (showProfile && profile) {
      priceLines.current.push(
        series.createPriceLine({
          price: profile.poc,
          color: token('--color-series-2'),
          lineWidth: 1,
          lineStyle: 0,
          axisLabelVisible: true,
          title: 'POC',
        }),
      )
    }
  }, [levels, profile, showLevels, showProfile])

  useEffect(() => {
    const plugin = markerPlugin.current
    const element = container.current
    if (!plugin || !element) return
    const token = (name: string) => getComputedStyle(element).getPropertyValue(name).trim()
    plugin.setMarkers(markers.map((marker) => toMarker(marker, token)))
  }, [markers])

  return <div ref={container} role="img" aria-label={ariaLabel} className="w-full" />
}

/** Tahmin işaretçisi: yön oku, rengi sonuçtan (isabet / ıska / henüz bekliyor). */
function toMarker(marker: PredictionMarker, token: (name: string) => string): SeriesMarker<Time> {
  const up = marker.pUp >= 0.5
  const color =
    marker.hit == null
      ? token('--color-neutral')
      : marker.hit
        ? token('--color-up')
        : token('--color-down')
  return {
    time: marker.time as UTCTimestamp,
    position: up ? 'belowBar' : 'aboveBar',
    shape: up ? 'arrowUp' : 'arrowDown',
    color,
    text: `%${Math.round(marker.pUp * 100)}`,
    size: 1,
  }
}

function toCandlestick(candle: Candle): CandlestickData<Time> {
  return {
    time: candle.time as UTCTimestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  }
}

/** Grafikteki EMA, backend ile aynı sözleşme: tohum = ilk tam pencerenin ortalaması. */
function emaLine(candles: Candle[], period: number): LineData<Time>[] {
  if (candles.length < period) return []
  const alpha = 2 / (period + 1)
  const seed = candles.slice(0, period).reduce((sum, c) => sum + c.close, 0) / period
  const first = candles[period - 1]
  if (!first) return []
  const out: LineData<Time>[] = [{ time: first.time as UTCTimestamp, value: seed }]
  let previous = seed
  for (const candle of candles.slice(period)) {
    previous = alpha * candle.close + (1 - alpha) * previous
    out.push({ time: candle.time as UTCTimestamp, value: previous })
  }
  return out
}
