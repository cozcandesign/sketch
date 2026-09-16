import { Link } from 'react-router'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { ProbabilityGauge } from '@/components/domain/ProbabilityGauge'
import { ConfidenceBadge } from '@/components/domain/ConfidenceBadge'
import { shortModelLabel } from '@/features/predictions/modelLabel'
import { useMarket } from '@/api/queries/market'
import { useLivePrice } from '@/store/prices'
import { formatPercent, formatPrice } from '@/lib/format'
import { relativeTime } from '@/lib/time'
import { useNow } from '@/lib/useNow'
import { tr } from '@/i18n/tr'
import { HORIZON_LABELS, type HorizonKey, type HorizonState } from '@/api/types'

/**
 * Bir ufkun özeti: canlı tahmin üstte ve vurgulu, referans tahminciler altında küçük.
 * Referanslar gizlenmez — canlı modülün yenmesi gereken çizgi onlar (K26).
 */
function HorizonBlock({ state, now }: { state: HorizonState | undefined; now: Date }) {
  const horizon = (state?.horizon ?? '30m') as HorizonKey
  const latestPerModel = new Map<string, HorizonState['predictions'][number]>()
  for (const prediction of state?.predictions ?? []) {
    if (!latestPerModel.has(prediction.model_version)) {
      latestPerModel.set(prediction.model_version, prediction)
    }
  }
  const predictions = [...latestPerModel.values()]
  const livePrediction = predictions.find((prediction) => prediction.source === 'live')
  const baselines = predictions.filter((prediction) => prediction.source !== 'live')
  const newest = livePrediction ?? predictions[0]

  return (
    <div className="flex flex-col gap-1 border-t border-border/60 pt-2">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium">{HORIZON_LABELS[horizon]}</span>
        {newest ? (
          <span className="num text-xs text-muted">
            {relativeTime(newest.as_of, now, { never: tr.status.never })}
          </span>
        ) : null}
      </div>
      {predictions.length === 0 ? (
        <span className="text-xs text-muted">{tr.dashboard.waitingPredictions}</span>
      ) : null}
      {livePrediction ? (
        <>
          <ProbabilityGauge pUp={livePrediction.p_up} label={tr.dashboard.live} />
          <div className="flex flex-wrap items-center gap-1">
            <ConfidenceBadge label={livePrediction.confidence_label} />
            {livePrediction.conflict ? <Badge tone="warn">{tr.coin.conflict}</Badge> : null}
            {livePrediction.veto_active ? <Badge tone="critical">{tr.coin.veto}</Badge> : null}
          </div>
        </>
      ) : null}
      {baselines.map((prediction) => (
        <ProbabilityGauge
          key={prediction.model_version}
          pUp={prediction.p_up}
          label={shortModelLabel(prediction.model_version)}
          compact
        />
      ))}
    </div>
  )
}

export function CoinCard({ symbol }: { symbol: string }) {
  const { data } = useMarket(symbol)
  const live = useLivePrice(symbol)
  const now = useNow()

  const price = live?.price ?? data?.price.last ?? null
  const change = live?.change24h ?? data?.price.change_24h ?? null
  const stale = live ? live.stale : (data?.price.stale ?? true)
  const changeTone = change == null ? 'text-muted' : change >= 0 ? 'text-up' : 'text-down'

  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div>
          <Link to={`/coin/${symbol}`} className="text-lg font-semibold hover:text-accent">
            {symbol}
          </Link>
          <div className="flex items-baseline gap-2">
            <span className="num text-lg">
              {price == null ? tr.dashboard.noPrice : formatPrice(price)}
            </span>
            <span className={`num text-sm ${changeTone}`}>
              {tr.dashboard.change24h} {formatPercent(change)}
            </span>
          </div>
        </div>
        {stale ? (
          <Badge tone="warn">{tr.dashboard.stale}</Badge>
        ) : (
          <Badge tone="up">{tr.status.connected}</Badge>
        )}
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-4">
        {(Object.keys(HORIZON_LABELS) as HorizonKey[]).map((horizon) => (
          <HorizonBlock
            key={horizon}
            state={data?.horizons.find((h) => h.horizon === horizon)}
            now={now}
          />
        ))}
      </div>

      {data ? (
        <div className="mt-2 flex flex-wrap gap-x-3 border-t border-border pt-2 text-xs text-muted">
          {data.coverage
            .filter((c) => c.count > 0)
            .map((c) => (
              <span key={c.interval} className="num">
                {c.interval}: {c.count}
              </span>
            ))}
          {data.coverage.every((c) => c.count === 0) ? (
            <span>{tr.dashboard.candles}: 0</span>
          ) : null}
        </div>
      ) : null}
    </Card>
  )
}
