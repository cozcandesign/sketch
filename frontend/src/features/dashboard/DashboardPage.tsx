import { PageFrame } from '@/components/ui/PageFrame'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { CoinCard } from '@/features/dashboard/CoinCard'
import { useSymbols } from '@/api/queries/market'
import { tr } from '@/i18n/tr'

export function DashboardPage() {
  const { data, isLoading, isError } = useSymbols()

  return (
    <PageFrame title={tr.nav.dashboard}>
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted">{tr.dashboard.referenceOnly}</p>
        {isError ? <Card>{tr.common.error}</Card> : null}
        {isLoading ? <Skeleton rows={4} /> : null}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data?.symbols.map((symbol) => (
            <CoinCard key={symbol} symbol={symbol} />
          ))}
        </div>
      </div>
    </PageFrame>
  )
}
