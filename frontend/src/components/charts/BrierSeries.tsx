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
 * Günlük Brier skoru. İki referans çizgi: 0.25 "hiç bilgi yok" ve referans tahmincilerin en iyisi.
 * Modüllerin yenmesi gereken çizgi ikincisidir; grafikte görünmezse karşılaştırma yapılamaz.
 */
export function BrierSeries({
  daily,
  baselineBrier = null,
}: {
  daily: Calibration['daily']
  baselineBrier?: number | null
}) {
  const data = daily.map((point) => ({
    day: point.day,
    brier: Number(point.brier.toFixed(4)),
    n: point.n,
  }))
  // Bilgisiz çizgi (0.25) her zaman görünür kalsın, üstte biraz pay bırak
  const maxValue = Math.max(UNINFORMED, baselineBrier ?? 0, ...data.map((d) => d.brier))
  const upperBound = Math.ceil((maxValue + 0.05) * 20) / 20

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
          domain={[0, upperBound]}
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
            position: 'insideTopLeft',
            fill: 'var(--color-muted)',
            fontSize: 10,
            dy: -6,
          }}
        />
        {baselineBrier == null ? null : (
          <ReferenceLine
            y={Number(baselineBrier.toFixed(4))}
            stroke="var(--color-series-2)"
            strokeDasharray="6 3"
            label={{
              // Sağa yaslanır: 0.25 çizgisi ile referans çizgisi yakın olduğunda etiketler
              // üst üste binmesin (iki çizgi de okunabilir kalsın).
              value: tr.calibration.referenceLine,
              position: 'insideBottomRight',
              fill: 'var(--color-series-2)',
              fontSize: 10,
              dy: 10,
            }}
          />
        )}
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
