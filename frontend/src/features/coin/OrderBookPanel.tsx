import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { MetricRow } from '@/components/domain/MetricRow'
import type { OrderflowPoint } from '@/api/types'
import { BOOK_BALANCED, recentAverage } from '@/features/coin/orderflowMath'
import { formatScore } from '@/lib/format'
import { tr } from '@/i18n/tr'

function tone(value: number | null): 'up' | 'down' | 'muted' {
  if (value == null || Math.abs(value) < BOOK_BALANCED) return 'muted'
  return value > 0 ? 'up' : 'down'
}

export function OrderBookPanel({ points }: { points: OrderflowPoint[] }) {
  const top20 = recentAverage(points, 'top20_imbalance')
  const depth1 = recentAverage(points, 'depth1pct_imbalance')
  const lead = top20 ?? depth1
  const label =
    lead == null || Math.abs(lead) < BOOK_BALANCED
      ? tr.orderflow.bookBalanced
      : lead > 0
        ? tr.orderflow.bookBidHeavy
        : tr.orderflow.bookAskHeavy

  return (
    <Card title={tr.orderflow.book}>
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <Badge tone={tone(lead) === 'muted' ? 'neutral' : tone(lead)}>{label}</Badge>
        </div>
        <MetricRow
          label={tr.orderflow.bookTop20}
          value={formatScore(top20, 3)}
          tone={tone(top20)}
        />
        <MetricRow
          label={tr.orderflow.bookDepth1}
          value={formatScore(depth1, 3)}
          tone={tone(depth1)}
        />
        <p className="pt-1 text-xs text-muted">{tr.orderflow.bookHint}</p>
      </div>
    </Card>
  )
}
