import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { MetricRow } from '@/components/domain/MetricRow'
import type { Funding, LongShort } from '@/api/types'
import { formatPercent, formatScore } from '@/lib/format'
import { formatTime } from '@/lib/time'
import { tr } from '@/i18n/tr'

/** |z| bu eşiği aşınca taraf "kalabalık" sayılır (ARCHITECTURE.md §8.3 ile aynı eşik). */
const CROWDED_Z = 1

const LS_LABEL: Record<string, string> = {
  global_account: tr.orderflow.lsGlobalAccount,
  top_account: tr.orderflow.lsTopAccount,
  top_position: tr.orderflow.lsTopPosition,
}

/**
 * Funding ve long/short aynı kartta: ikisi de "hangi taraf kalabalık" sorusunu yanıtlar
 * (ARCHITECTURE.md §8.3 — long/short ayrı bileşen değildir).
 */
export function FundingPanel({ funding, longShort }: { funding: Funding; longShort: LongShort[] }) {
  const z = funding.zscore
  const crowded = z != null && Math.abs(z) >= CROWDED_Z
  const label = !crowded
    ? tr.orderflow.fundingNeutral
    : (z ?? 0) > 0
      ? tr.orderflow.fundingLongCrowded
      : tr.orderflow.fundingShortCrowded

  return (
    <Card title={tr.orderflow.funding}>
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <Badge tone={!crowded ? 'neutral' : (z ?? 0) > 0 ? 'down' : 'up'}>{label}</Badge>
        </div>
        <MetricRow
          label={tr.orderflow.fundingRate}
          value={formatPercent(funding.last_rate, 4)}
          tone={funding.last_rate == null ? 'muted' : funding.last_rate >= 0 ? 'up' : 'down'}
        />
        <MetricRow
          label={tr.orderflow.fundingAverage}
          value={formatPercent(funding.average_30d, 4)}
          tone="muted"
        />
        <MetricRow label={tr.orderflow.fundingZ} value={formatScore(z, 2)} />
        <MetricRow
          label={tr.orderflow.fundingNext}
          value={funding.next_funding_time ? formatTime(funding.next_funding_time) : '—'}
          tone="muted"
        />
        <p className="pt-1 text-xs text-muted">{tr.orderflow.fundingHint}</p>
        {longShort.length === 0 ? null : (
          <div className="mt-2 flex flex-col gap-1 border-t border-border pt-2">
            <span className="text-xs uppercase tracking-wide text-muted">
              {tr.orderflow.longShort}
            </span>
            {longShort.map((row) => (
              <MetricRow
                key={row.kind}
                label={LS_LABEL[row.kind] ?? row.kind}
                value={formatScore(row.ratio, 2)}
                tone={row.ratio > 1 ? 'up' : row.ratio < 1 ? 'down' : 'muted'}
              />
            ))}
            <p className="text-xs text-muted">{tr.orderflow.lsHint}</p>
          </div>
        )}
      </div>
    </Card>
  )
}
