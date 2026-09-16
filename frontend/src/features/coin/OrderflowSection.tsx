import { useState } from 'react'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Select'
import { Skeleton } from '@/components/ui/Skeleton'
import { CVDPanel } from '@/features/coin/CVDPanel'
import { FundingPanel } from '@/features/coin/FundingPanel'
import { LiquidationPanel } from '@/features/coin/LiquidationPanel'
import { OIPanel } from '@/features/coin/OIPanel'
import { OrderBookPanel } from '@/features/coin/OrderBookPanel'
import { useOrderflow } from '@/api/queries/orderflow'
import { formatProbability } from '@/lib/format'
import { tr } from '@/i18n/tr'

const WINDOWS = [60, 240, 720, 1440] as const
const DEFAULT_WINDOW = 240
/** Bunun altındaki kapsama uyarı rengiyle gösterilir: paneldeki sayılar eksik veriyle hesaplanmıştır. */
const COVERAGE_WARN = 0.9

export function OrderflowSection({
  symbol,
  priceChange24h,
}: {
  symbol: string
  priceChange24h: number | null
}) {
  const [minutes, setMinutes] = useState<number>(DEFAULT_WINDOW)
  const orderflow = useOrderflow(symbol, minutes)
  const data = orderflow.data
  const coverage = data?.coverage_ratio ?? null

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-xs uppercase tracking-wide text-muted">{tr.orderflow.title}</h2>
          {coverage == null ? null : (
            <Badge tone={coverage < COVERAGE_WARN ? 'warn' : 'neutral'}>
              {`${tr.orderflow.coverage} ${formatProbability(coverage)}`}
            </Badge>
          )}
        </div>
        <Select
          label={tr.orderflow.windowLabel}
          value={String(minutes)}
          options={WINDOWS.map((value) => ({ value: String(value), label: `${value} dk` }))}
          onChange={(value) => setMinutes(Number(value))}
        />
      </div>

      {coverage != null && coverage < COVERAGE_WARN ? (
        <p className="text-xs text-warn">{tr.orderflow.coverageHint}</p>
      ) : null}

      {orderflow.isLoading || !data ? (
        <Card>
          <Skeleton rows={4} />
        </Card>
      ) : data.minutes.length === 0 && data.funding.last_rate == null ? (
        <Card>
          <p className="text-sm text-muted">{tr.orderflow.noData}</p>
        </Card>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          <FundingPanel funding={data.funding} longShort={data.long_short} />
          <OIPanel openInterest={data.open_interest} priceChange24h={priceChange24h} />
          <LiquidationPanel points={data.minutes} />
          <OrderBookPanel points={data.minutes} />
          <div className="lg:col-span-2">
            <CVDPanel points={data.minutes} />
          </div>
        </div>
      )}
    </div>
  )
}
