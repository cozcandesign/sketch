import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { MetricRow } from '@/components/domain/MetricRow'
import type { OpenInterest } from '@/api/types'
import { oiState, type OiState } from '@/features/coin/orderflowMath'
import { formatCount, formatPercent, formatUsdCompact } from '@/lib/format'
import { tr } from '@/i18n/tr'

const STATE_LABEL: Record<NonNullable<OiState>, string> = {
  realBuying: tr.orderflow.oiRealBuying,
  shortBuilding: tr.orderflow.oiShortBuilding,
  shortCovering: tr.orderflow.oiShortCovering,
  longUnwinding: tr.orderflow.oiLongUnwinding,
}

const STATE_TONE: Record<NonNullable<OiState>, 'up' | 'down'> = {
  realBuying: 'up',
  shortBuilding: 'down',
  shortCovering: 'up',
  longUnwinding: 'down',
}

export function OIPanel({
  openInterest,
  priceChange24h,
}: {
  openInterest: OpenInterest
  priceChange24h: number | null
}) {
  const state = oiState(openInterest.change_24h, priceChange24h)

  return (
    <Card title={tr.orderflow.openInterest}>
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          {state ? <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge> : null}
        </div>
        <MetricRow
          label={tr.orderflow.oiLatest}
          value={
            openInterest.latest_usd == null
              ? formatCount(openInterest.latest)
              : `${formatCount(openInterest.latest)} · ${formatUsdCompact(openInterest.latest_usd)}`
          }
          tone={openInterest.latest == null ? 'muted' : 'text'}
        />
        <MetricRow
          label={tr.orderflow.oiChange}
          value={formatPercent(openInterest.change_24h)}
          tone={
            openInterest.change_24h == null ? 'muted' : openInterest.change_24h >= 0 ? 'up' : 'down'
          }
        />
        <MetricRow
          label={tr.orderflow.priceChange}
          value={formatPercent(priceChange24h)}
          tone={priceChange24h == null ? 'muted' : priceChange24h >= 0 ? 'up' : 'down'}
        />
        <p className="pt-1 text-xs text-muted">{tr.orderflow.oiHint}</p>
      </div>
    </Card>
  )
}
