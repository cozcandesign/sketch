import { Drawer } from '@/components/ui/Drawer'
import { Skeleton } from '@/components/ui/Skeleton'
import { ProbabilityGauge } from '@/components/domain/ProbabilityGauge'
import { ConfidenceBadge } from '@/components/domain/ConfidenceBadge'
import { HitBadge, OutcomeBadge } from '@/components/domain/OutcomeBadge'
import { usePrediction } from '@/api/queries/predictions'
import { modelLabel } from '@/features/predictions/modelLabel'
import { formatPercent, formatPrice, formatScore } from '@/lib/format'
import { formatDateTime } from '@/lib/time'
import { HORIZON_LABELS, type HorizonKey } from '@/api/types'
import { tr } from '@/i18n/tr'

interface Reason {
  module?: string
  text?: string
}

export function PredictionDrawer({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { data, isLoading } = usePrediction(id)
  const columns = tr.predictions.columns
  const reasons = (data?.report?.reasons as Reason[] | undefined) ?? []

  return (
    <Drawer
      title={tr.predictions.detail.title}
      open={id != null}
      onClose={onClose}
      closeLabel={tr.predictions.detail.close}
    >
      {isLoading || !data ? (
        <Skeleton rows={5} />
      ) : (
        <div className="flex flex-col gap-3">
          <div>
            <div className="text-sm font-semibold">
              {data.symbol} · {HORIZON_LABELS[data.horizon as HorizonKey] ?? data.horizon} ·{' '}
              {modelLabel(data.model_version)}
            </div>
            <div className="num text-xs text-muted">
              {formatDateTime(data.as_of)} → {formatDateTime(data.target_at)}
            </div>
          </div>

          <ProbabilityGauge pUp={data.p_up} />
          <div className="flex items-center gap-2">
            <ConfidenceBadge label={data.confidence_label} />
            <OutcomeBadge outcome={data.outcome} />
            <HitBadge hit={data.outcome?.hit} />
          </div>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted">{columns.priceAt}</dt>
            <dd className="num text-right">{formatPrice(data.price_at)}</dd>
            <dt className="text-muted">{columns.priceTarget}</dt>
            <dd className="num text-right">{formatPrice(data.outcome?.price_at_target)}</dd>
            <dt className="text-muted">{columns.change}</dt>
            <dd className="num text-right">{formatPercent(data.outcome?.realized_return)}</dd>
            <dt className="text-muted">{columns.brier}</dt>
            <dd className="num text-right">{formatScore(data.outcome?.brier)}</dd>
          </dl>

          <section>
            <h3 className="mb-1 text-xs uppercase tracking-wide text-muted">
              {tr.predictions.detail.rationale}
            </h3>
            {reasons.length > 0 ? (
              <ul className="flex list-disc flex-col gap-1 pl-4 text-sm">
                {reasons.map((reason, index) => (
                  <li key={index}>{reason.text}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">{tr.predictions.detail.noReport}</p>
            )}
          </section>
        </div>
      )}
    </Drawer>
  )
}
