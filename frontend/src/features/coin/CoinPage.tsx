import { useState } from 'react'
import { useParams } from 'react-router'
import { PageFrame } from '@/components/ui/PageFrame'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Select } from '@/components/ui/Select'
import { Skeleton } from '@/components/ui/Skeleton'
import { CandleChart } from '@/components/charts/CandleChart'
import { ModuleBreakdown } from '@/components/domain/ModuleBreakdown'
import { ReportCard } from '@/components/domain/ReportCard'
import { HorizonTabs } from '@/features/coin/HorizonTabs'
import { LevelTable } from '@/features/coin/LevelTable'
import { OverlayToggles, type Overlays } from '@/features/coin/OverlayToggles'
import { useCandles, useMarket } from '@/api/queries/market'
import { useSignals, useLevels } from '@/api/queries/signals'
import { usePredictions } from '@/api/queries/predictions'
import { useLivePrice } from '@/store/prices'
import { formatPercent, formatPrice } from '@/lib/format'
import {
  CHART_INTERVALS,
  HORIZONS,
  HORIZON_LABELS,
  type HorizonKey,
  type IntervalKey,
} from '@/api/types'
import { tr } from '@/i18n/tr'

const CANDLE_LIMIT = 400

export function CoinPage() {
  const { symbol = '' } = useParams()
  const [interval, setInterval] = useState<IntervalKey>('15m')
  const [horizon, setHorizon] = useState<HorizonKey>('1h')
  const [overlays, setOverlays] = useState<Overlays>({ ema: true, levels: true, profile: true })

  const market = useMarket(symbol)
  const candles = useCandles(symbol, interval, CANDLE_LIMIT)
  const signals = useSignals(symbol)
  const levels = useLevels(symbol, interval)
  const history = usePredictions({ symbol, horizon })
  const live = useLivePrice(symbol)

  const price = live?.price ?? market.data?.price.last ?? null
  const change = live?.change24h ?? market.data?.price.change_24h ?? null
  const selected = signals.data?.horizons.find((item) => item.horizon === horizon)
  const markers = (history.data?.pages ?? [])
    .flatMap((page) => page.items)
    .filter((prediction) => prediction.source === 'live')
    .map((prediction) => ({
      time: Math.floor(new Date(prediction.as_of).getTime() / 1000),
      pUp: prediction.p_up,
      hit: prediction.outcome?.hit ?? null,
    }))

  return (
    <PageFrame title={`${symbol}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <span className="num text-lg">
            {price == null ? tr.dashboard.noPrice : formatPrice(price)}
          </span>
          <span
            className={`num text-sm ${change == null ? 'text-muted' : change >= 0 ? 'text-up' : 'text-down'}`}
          >
            {tr.dashboard.change24h} {formatPercent(change)}
          </span>
          {market.data?.price.stale ? <Badge tone="warn">{tr.dashboard.stale}</Badge> : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Select
            label={tr.coin.interval}
            value={interval}
            options={CHART_INTERVALS.map((value) => ({ value, label: value }))}
            onChange={(value) => setInterval(value as IntervalKey)}
          />
          <OverlayToggles value={overlays} onChange={setOverlays} />
        </div>
      </div>

      <Card title={tr.coin.chart}>
        {candles.isLoading ? (
          <Skeleton rows={6} />
        ) : (candles.data?.candles.length ?? 0) === 0 ? (
          <p className="text-sm text-muted">{tr.coin.noCandles}</p>
        ) : (
          <CandleChart
            candles={candles.data?.candles ?? []}
            levels={levels.data?.levels ?? []}
            profile={levels.data?.volume_profile ?? null}
            markers={markers}
            showEma={overlays.ema}
            showLevels={overlays.levels}
            showProfile={overlays.profile}
            ariaLabel={`${symbol} ${tr.coin.chart} ${interval}`}
          />
        )}
      </Card>

      <HorizonTabs
        value={horizon}
        onChange={setHorizon}
        horizons={HORIZONS}
        labels={HORIZON_LABELS}
      />

      <div className="grid gap-3 lg:grid-cols-2">
        {signals.isLoading || !selected ? (
          <Card>
            <Skeleton rows={4} />
          </Card>
        ) : (
          <ReportCard horizon={selected} />
        )}

        <Card title={tr.coin.modules}>
          {signals.isLoading ? (
            <Skeleton rows={4} />
          ) : (
            <div className="flex flex-col gap-3">
              <ModuleBreakdown modules={selected?.modules ?? []} />
              <p className="text-xs text-muted">{tr.coin.singleModuleWarning}</p>
            </div>
          )}
        </Card>
      </div>

      <Card title={tr.coin.levelsTitle}>
        <LevelTable levels={levels.data ?? null} />
      </Card>
    </PageFrame>
  )
}
