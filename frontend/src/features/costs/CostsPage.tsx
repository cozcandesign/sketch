import { PageFrame } from '@/components/ui/PageFrame'
import { Card } from '@/components/ui/Card'
import { tr } from '@/i18n/tr'

export function CostsPage() {
  return (
    <PageFrame title={tr.nav.costs}>
      <Card>
        <p className="text-muted">{tr.placeholder.phase.replace('{phase}', '4')}</p>
      </Card>
    </PageFrame>
  )
}
