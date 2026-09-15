import { useState } from 'react'
import { PageFrame } from '@/components/ui/PageFrame'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { Skeleton } from '@/components/ui/Skeleton'
import { Table, Td, Th, Tr } from '@/components/ui/Table'
import { CalibrationCurve } from '@/components/charts/CalibrationCurve'
import { BrierSeries } from '@/components/charts/BrierSeries'
import { useCalibration, type CalibrationWindow } from '@/api/queries/calibration'
import { formatCount, formatProbability, formatScore } from '@/lib/format'
import type { HorizonSummary, ModelSummary } from '@/api/types'
import { tr } from '@/i18n/tr'

const WINDOWS: CalibrationWindow[] = ['7d', '30d', '90d', 'all']

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-sm border border-border bg-surface-2 px-3 py-2">
      <div className="text-xs text-muted">{label}</div>
      <div className="num text-lg">{value}</div>
      {hint ? <div className="text-xs text-muted">{hint}</div> : null}
    </div>
  )
}

function SummaryRows({ rows }: { rows: (ModelSummary | HorizonSummary)[] }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>{tr.predictions.columns.model}</Th>
          <Th align="right">{tr.calibration.sampleCount}</Th>
          <Th align="right">{tr.calibration.brier}</Th>
          <Th align="right">{tr.calibration.hitRate}</Th>
          <Th align="right">{tr.calibration.ciLabel}</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <Tr key={row.label_tr}>
            <Td>{row.label_tr}</Td>
            <Td align="right" mono>
              {formatCount(row.n)}
            </Td>
            <Td align="right" mono>
              {formatScore(row.brier)}
            </Td>
            <Td align="right" mono>
              {formatProbability(row.hit_rate)}
            </Td>
            <Td align="right" mono>
              {row.hit_ci_low == null
                ? tr.common.none
                : `${formatProbability(row.hit_ci_low)} – ${formatProbability(row.hit_ci_high)}`}
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

export function CalibrationPage() {
  const [window, setWindow] = useState<CalibrationWindow>('30d')
  const { data, isLoading } = useCalibration(window)
  const hasData = (data?.overall.n ?? 0) > 0

  return (
    <PageFrame title={tr.calibration.title}>
      <div className="flex flex-col gap-3">
        <p className="max-w-3xl text-xs text-muted">{tr.calibration.explainer}</p>

        <Select
          label={tr.calibration.window}
          value={window}
          onChange={(value) => setWindow(value as CalibrationWindow)}
          options={WINDOWS.map((w) => ({ value: w, label: tr.calibration.windows[w] }))}
        />

        {isLoading ? <Skeleton rows={4} /> : null}

        {data ? (
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile label={tr.calibration.resolved} value={formatCount(data.overall.n)} />
            <StatTile label={tr.calibration.pending} value={formatCount(data.pending)} />
            <StatTile
              label={tr.calibration.brier}
              value={formatScore(data.overall.brier)}
              hint={tr.calibration.uninformed}
            />
            <StatTile
              label={tr.calibration.hitRate}
              value={formatProbability(data.overall.hit_rate)}
              hint={
                data.overall.hit_ci_low == null
                  ? undefined
                  : `${formatProbability(data.overall.hit_ci_low)} – ${formatProbability(
                      data.overall.hit_ci_high,
                    )}`
              }
            />
          </div>
        ) : null}

        {data && !hasData ? <Card>{tr.calibration.empty}</Card> : null}

        {data && hasData ? (
          <>
            <div className="grid gap-3 xl:grid-cols-2">
              <Card title={tr.calibration.curve}>
                <CalibrationCurve bins={data.bins} />
              </Card>
              <Card title={tr.calibration.series}>
                <BrierSeries daily={data.daily} />
              </Card>
            </div>
            <div className="grid gap-3 xl:grid-cols-2">
              <Card title={tr.calibration.byModel}>
                <SummaryRows rows={data.by_model} />
              </Card>
              <Card title={tr.calibration.byHorizon}>
                <SummaryRows rows={data.by_horizon} />
              </Card>
            </div>
          </>
        ) : null}
      </div>
    </PageFrame>
  )
}
