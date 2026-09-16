import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card } from '@/components/ui/Card'
import { MetricRow } from '@/components/domain/MetricRow'
import type { OrderflowPoint } from '@/api/types'
import { bucketLiquidations } from '@/features/coin/orderflowMath'
import { formatUsdCompact } from '@/lib/format'
import { formatTime } from '@/lib/time'
import { tr } from '@/i18n/tr'

export function LiquidationPanel({ points }: { points: OrderflowPoint[] }) {
  const buckets = bucketLiquidations(points)
  const totalLong = buckets.reduce((sum, bucket) => sum + bucket.long, 0)
  const totalShort = buckets.reduce((sum, bucket) => sum + bucket.short, 0)
  const empty = totalLong === 0 && totalShort === 0

  return (
    <Card title={tr.orderflow.liquidations}>
      <div className="flex flex-col gap-1">
        <MetricRow
          label={tr.orderflow.liqLong}
          value={formatUsdCompact(totalLong)}
          tone={totalLong > 0 ? 'down' : 'muted'}
        />
        <MetricRow
          label={tr.orderflow.liqShort}
          value={formatUsdCompact(totalShort)}
          tone={totalShort > 0 ? 'up' : 'muted'}
        />
        {empty ? (
          <p className="py-2 text-sm text-muted">{tr.orderflow.liqNone}</p>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={buckets} margin={{ top: 8, right: 8, bottom: 4, left: 4 }}>
              <CartesianGrid stroke="var(--color-grid)" strokeDasharray="2 4" />
              <XAxis
                dataKey="ts"
                stroke="var(--color-muted)"
                tick={{ fontSize: 10 }}
                tickFormatter={(value: string) => formatTime(value)}
                minTickGap={24}
              />
              <YAxis
                stroke="var(--color-muted)"
                tick={{ fontSize: 10 }}
                width={70}
                tickFormatter={(value: number) => formatUsdCompact(value)}
              />
              <Tooltip
                cursor={{ fill: 'var(--color-surface-2)' }}
                labelFormatter={(value) => (typeof value === 'string' ? formatTime(value) : '')}
                formatter={(value, name) => [
                  typeof value === 'number' ? formatUsdCompact(value) : '—',
                  name,
                ]}
                contentStyle={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 4,
                  fontSize: 12,
                }}
              />
              <Bar
                dataKey="long"
                name={tr.orderflow.liqLong}
                fill="var(--color-down)"
                isAnimationActive={false}
                stackId="liq"
              />
              <Bar
                dataKey="short"
                name={tr.orderflow.liqShort}
                fill="var(--color-up)"
                isAnimationActive={false}
                stackId="liq"
              />
            </BarChart>
          </ResponsiveContainer>
        )}
        <p className="pt-1 text-xs text-muted">{tr.orderflow.liqHint}</p>
      </div>
    </Card>
  )
}
