import { useState } from 'react'
import { PageFrame } from '@/components/ui/PageFrame'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Skeleton } from '@/components/ui/Skeleton'
import { PredictionTable } from '@/features/predictions/PredictionTable'
import { PredictionDrawer } from '@/features/predictions/PredictionDrawer'
import { usePredictions, type PredictionFilters } from '@/api/queries/predictions'
import { useSymbols } from '@/api/queries/market'
import { HORIZON_LABELS, HORIZONS } from '@/api/types'
import { tr } from '@/i18n/tr'

export function PredictionsPage() {
  const [filters, setFilters] = useState<PredictionFilters>({ status: 'all' })
  const [selected, setSelected] = useState<number | null>(null)
  const { data: symbolData } = useSymbols()
  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } =
    usePredictions(filters)

  const rows = data?.pages.flatMap((page) => page.items) ?? []

  return (
    <PageFrame title={tr.predictions.title}>
      <div className="flex h-full flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Select
            label={tr.predictions.filters.symbol}
            value={filters.symbol ?? ''}
            onChange={(value) => setFilters({ ...filters, symbol: value || undefined })}
            options={[
              { value: '', label: tr.predictions.filters.all },
              ...(symbolData?.symbols ?? []).map((s) => ({ value: s, label: s })),
            ]}
          />
          <Select
            label={tr.predictions.filters.horizon}
            value={filters.horizon ?? ''}
            onChange={(value) => setFilters({ ...filters, horizon: value || undefined })}
            options={[
              { value: '', label: tr.predictions.filters.all },
              ...HORIZONS.map((h) => ({ value: h, label: HORIZON_LABELS[h] })),
            ]}
          />
          <Select
            label={tr.predictions.filters.status}
            value={filters.status ?? 'all'}
            onChange={(value) =>
              setFilters({ ...filters, status: value as PredictionFilters['status'] })
            }
            options={[
              { value: 'all', label: tr.predictions.filters.all },
              { value: 'active', label: tr.predictions.filters.active },
              { value: 'resolved', label: tr.predictions.filters.resolved },
            ]}
          />
        </div>

        {isLoading ? <Skeleton rows={6} /> : null}
        {!isLoading && rows.length === 0 ? <Card>{tr.predictions.empty}</Card> : null}
        {rows.length > 0 ? (
          <Card className="min-h-0 flex-1 overflow-auto">
            <PredictionTable rows={rows} onSelect={setSelected} />
            {hasNextPage ? (
              <div className="mt-2">
                <Button onClick={() => void fetchNextPage()} disabled={isFetchingNextPage}>
                  {isFetchingNextPage ? tr.common.loading : tr.predictions.loadMore}
                </Button>
              </div>
            ) : null}
          </Card>
        ) : null}
      </div>
      <PredictionDrawer id={selected} onClose={() => setSelected(null)} />
    </PageFrame>
  )
}
