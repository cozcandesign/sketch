import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { ProbabilityGauge } from '@/components/domain/ProbabilityGauge'
import { ConfidenceBadge } from '@/components/domain/ConfidenceBadge'
import { RationaleList } from '@/components/domain/RationaleList'
import { formatPrice } from '@/lib/format'
import { formatDateTime } from '@/lib/time'
import type { HorizonSignals } from '@/api/types'
import { tr } from '@/i18n/tr'

interface Reason {
  module?: string
  text?: string
  weight?: number
}

interface Report {
  headline?: string
  reasons?: Reason[]
  counter_argument?: string
  expected_range?: { low: number; high: number } | null
  missing?: string[]
}

/** Tek ufkun raporu: başlık, olasılık, gerekçeler, karşıt argüman, beklenen aralık. */
export function ReportCard({ horizon }: { horizon: HorizonSignals }) {
  const report = (horizon.report ?? {}) as Report
  const reasons = (report.reasons ?? []).map((reason) => reason.text ?? '').filter(Boolean)

  if (horizon.p_up == null) {
    return (
      <Card>
        <p className="text-sm text-muted">{tr.coin.noPrediction}</p>
      </Card>
    )
  }

  return (
    <Card>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold">{report.headline}</span>
          <div className="flex items-center gap-1.5">
            {horizon.confidence_label ? <ConfidenceBadge label={horizon.confidence_label} /> : null}
            {horizon.conflict ? <Badge tone="warn">{tr.coin.conflict}</Badge> : null}
            {horizon.veto_active ? <Badge tone="critical">{tr.coin.veto}</Badge> : null}
          </div>
        </div>

        <ProbabilityGauge pUp={horizon.p_up} />

        <div>
          <h3 className="mb-1 text-xs uppercase tracking-wide text-muted">{tr.coin.rationale}</h3>
          <RationaleList items={reasons} />
        </div>

        {report.counter_argument ? (
          <div className="rounded-sm border border-border bg-surface-2 p-2">
            <h3 className="mb-0.5 text-xs uppercase tracking-wide text-muted">
              {tr.coin.counterArgument}
            </h3>
            <p className="text-sm">{report.counter_argument}</p>
          </div>
        ) : null}

        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted">{tr.coin.expectedRange}</dt>
          <dd className="num text-right">
            {report.expected_range
              ? `${formatPrice(report.expected_range.low)} – ${formatPrice(report.expected_range.high)}`
              : tr.common.none}
          </dd>
          <dt className="text-muted">{tr.coin.asOf}</dt>
          <dd className="num text-right">
            {horizon.as_of ? formatDateTime(horizon.as_of) : tr.common.none}
          </dd>
        </dl>

        {report.missing && report.missing.length > 0 ? (
          <p className="text-xs text-muted">
            {tr.coin.missingModules}: {report.missing.join(', ')}
          </p>
        ) : null}
      </div>
    </Card>
  )
}
