import { Link } from 'react-router'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { ProbabilityGauge } from '@/components/domain/ProbabilityGauge'
import { ConfidenceBadge } from '@/components/domain/ConfidenceBadge'
import { useMarket } from '@/api/queries/market'
import { useLivePrice } from '@/store/prices'
import { formatPercent, formatPrice } from '@/lib/format'
import { relativeTime } from '@/lib/time'
import { useNow } from '@/lib/useNow'
import { tr } from '@/i18n/tr'
import { HORIZON_LABELS, type HorizonKey } from '@/api/types'

export function CoinCard({ symbol }: { symbol: string }) {
  const { data, isLoading } = useMarket(symbol)
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

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
        {(Object.keys(HORIZON_LABELS) as HorizonKey[]).map((horizon) => {
          const state = data?.horizons.find((h) => h.horizon === horizon)
          const prediction = state?.predictions[0]
          return (
            <div key={horizon} className="flex flex-col gap-1">
              {prediction ? (
                <>
                  <ProbabilityGauge pUp={prediction.p_up} label={HORIZON_LABELS[horizon]} compact />
                  <div className="flex items-center justify-between">
                    <ConfidenceBadge label={prediction.confidence_label} />
                    <span className="num text-xs text-muted">
                      {relativeTime(prediction.as_of, now, { never: tr.status.never })}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-muted">{HORIZON_LABELS[horizon]}</span>
                  <span className="text-xs text-muted">
                    {isLoading ? tr.common.loading : tr.dashboard.waitingPredictions}
                  </span>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {data ? (
        <div className="mt-3 flex gap-3 border-t border-border pt-2 text-xs text-muted">
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
