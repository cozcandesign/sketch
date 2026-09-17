import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card } from '@/components/ui/Card'
import { MetricRow } from '@/components/domain/MetricRow'
import type { OrderflowPoint } from '@/api/types'
import { flowRatio } from '@/features/coin/orderflowMath'
import { formatCount, formatPercent, formatScore } from '@/lib/format'
import { formatTime } from '@/lib/time'
import { tr } from '@/i18n/tr'

export function CVDPanel({ points }: { points: OrderflowPoint[] }) {
  const data = points.map((point) => ({
    ts: point.ts,
    cvd: point.cvd_cumulative,
  }))
  const net = points.reduce((sum, point) => sum + (point.cvd_delta ?? 0), 0)
  const ratio = flowRatio(points)
  // İşlem sayısı ayrı gösterilir: sıfırsa sorun "akış sakin" değil, aggTrade akışı gelmiyordur.
  const trades = points.reduce((sum, point) => sum + (point.trade_count ?? 0), 0)

  return (
    <Card title={tr.orderflow.cvd}>
      <div className="flex flex-col gap-1">
        <MetricRow
          label={tr.orderflow.cvdWindow}
          value={formatScore(net, 2)}
          tone={net === 0 ? 'muted' : net > 0 ? 'up' : 'down'}
        />
        <MetricRow
          label={tr.orderflow.cvdRatio}
          value={formatPercent(ratio)}
          tone={ratio == null ? 'muted' : ratio > 0 ? 'up' : 'down'}
        />
        <MetricRow
          label={tr.orderflow.cvdTrades}
          value={formatCount(trades)}
          tone={trades === 0 ? 'muted' : 'text'}
          title={tr.orderflow.cvdTradesHint}
        />
        {data.length === 0 ? null : (
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 4 }}>
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
                width={54}
                tickFormatter={(value: number) => formatScore(value, 0)}
              />
              <ReferenceLine y={0} stroke="var(--color-border)" />
              <Tooltip
                cursor={{ stroke: 'var(--color-border)' }}
                labelFormatter={(value) => (typeof value === 'string' ? formatTime(value) : '')}
                formatter={(value, name) => [
                  typeof value === 'number' ? formatScore(value, 2) : '—',
                  name,
                ]}
                contentStyle={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 4,
                  fontSize: 12,
                }}
              />
              <Line
                type="monotone"
                dataKey="cvd"
                name={tr.orderflow.cvd}
                stroke="var(--color-series-1)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
        <p className="pt-1 text-xs text-muted">{tr.orderflow.cvdHint}</p>
      </div>
    </Card>
  )
}
