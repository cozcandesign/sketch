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
import type { Calibration } from '@/api/types'
import { tr } from '@/i18n/tr'

const UNINFORMED = 0.25

/**
 * Günlük Brier skoru. 0.25 çizgisi "hiç bilgi yok" seviyesidir; çizginin altı iyidir.
 * Tek seri olduğu için lejant yok; başlık seriyi adlandırır.
 */
export function BrierSeries({ daily }: { daily: Calibration['daily'] }) {
  const data = daily.map((point) => ({
    day: point.day,
    brier: Number(point.brier.toFixed(4)),
    n: point.n,
  }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid stroke="var(--color-grid)" strokeDasharray="2 4" />
        <XAxis
          dataKey="day"
          stroke="var(--color-muted)"
          tick={{ fontSize: 11 }}
          tickFormatter={(value: string) => value.slice(5)}
        />
        <YAxis
          domain={[0, 'auto']}
          stroke="var(--color-muted)"
          tick={{ fontSize: 11 }}
          width={44}
        />
        <ReferenceLine
          y={UNINFORMED}
          stroke="var(--color-muted)"
          strokeDasharray="4 4"
          label={{
            value: tr.calibration.uninformed,
            position: 'insideTopRight',
            fill: 'var(--color-muted)',
            fontSize: 10,
          }}
        />
        <Tooltip
          cursor={{ stroke: 'var(--color-border)' }}
          contentStyle={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 4,
            fontSize: 12,
          }}
        />
        <Line
          type="monotone"
          dataKey="brier"
          name={tr.calibration.brier}
          stroke="var(--color-series-1)"
          strokeWidth={2}
          dot={{
            r: 4,
            fill: 'var(--color-series-1)',
            stroke: 'var(--color-surface)',
            strokeWidth: 2,
          }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
