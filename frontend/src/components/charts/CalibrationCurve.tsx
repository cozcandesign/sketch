import {
  CartesianGrid,
  Legend,
  ReferenceLine,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
  ResponsiveContainer,
} from 'recharts'
import type { CalibrationBin } from '@/api/types'
import { tr } from '@/i18n/tr'

/**
 * Kalibrasyon eğrisi: "söylediğim olasılık" (x) ile "gerçekleşen oran" (y).
 * Köşegen mükemmel kalibrasyondur; noktalar köşegene ne kadar yakınsa o kadar iyi.
 * Nokta büyüklüğü o kovadaki örnek sayısını gösterir.
 */
export function CalibrationCurve({ bins }: { bins: CalibrationBin[] }) {
  const points = bins
    .filter((bin) => bin.n > 0 && bin.mean_p != null && bin.observed_freq != null)
    .map((bin) => ({ x: bin.mean_p as number, y: bin.observed_freq as number, n: bin.n }))

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
        <CartesianGrid stroke="var(--color-grid)" strokeDasharray="2 4" />
        <XAxis
          type="number"
          dataKey="x"
          domain={[0, 1]}
          ticks={[0, 0.25, 0.5, 0.75, 1]}
          tickFormatter={(value: number) => `%${Math.round(value * 100)}`}
          stroke="var(--color-muted)"
          tick={{ fontSize: 11 }}
          label={{
            value: tr.dashboard.horizonHeader,
            position: 'insideBottom',
            offset: -12,
            fill: 'var(--color-muted)',
            fontSize: 11,
          }}
        />
        <YAxis
          type="number"
          dataKey="y"
          domain={[0, 1]}
          ticks={[0, 0.25, 0.5, 0.75, 1]}
          tickFormatter={(value: number) => `%${Math.round(value * 100)}`}
          stroke="var(--color-muted)"
          tick={{ fontSize: 11 }}
          width={44}
          label={{
            value: tr.calibration.observed,
            angle: -90,
            position: 'insideLeft',
            fill: 'var(--color-muted)',
            fontSize: 11,
          }}
        />
        <ZAxis type="number" dataKey="n" range={[40, 320]} name={tr.calibration.sampleCount} />
        <ReferenceLine
          segment={[
            { x: 0, y: 0 },
            { x: 1, y: 1 },
          ]}
          stroke="var(--color-muted)"
          strokeDasharray="4 4"
          ifOverflow="extendDomain"
        />
        <Tooltip
          cursor={{ stroke: 'var(--color-border)' }}
          contentStyle={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 4,
            fontSize: 12,
          }}
          formatter={(value, name) =>
            typeof value === 'number' && name !== tr.calibration.sampleCount
              ? [`%${Math.round(value * 100)}`, name]
              : [String(value ?? ''), name]
          }
        />
        <Legend
          verticalAlign="top"
          height={24}
          wrapperStyle={{ fontSize: 11, color: 'var(--color-muted)' }}
        />
        <Scatter
          name={tr.calibration.observed}
          data={points}
          fill="var(--color-series-1)"
          stroke="var(--color-surface)"
          strokeWidth={2}
        />
      </ScatterChart>
    </ResponsiveContainer>
  )
}
