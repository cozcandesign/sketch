import { PageFrame } from '@/components/ui/PageFrame'
import { Card } from '@/components/ui/Card'
import { tr } from '@/i18n/tr'

export function CoinPage() {
  return (
    <PageFrame title={tr.nav.coin}>
      <Card>
        <p className="text-muted">{tr.placeholder.phase.replace('{phase}', '2')}</p>
      </Card>
    </PageFrame>
  )
}
