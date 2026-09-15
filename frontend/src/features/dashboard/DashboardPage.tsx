import { PageFrame } from '@/components/ui/PageFrame'
import { Card } from '@/components/ui/Card'
import { tr } from '@/i18n/tr'

export function DashboardPage() {
  return (
    <PageFrame title={tr.nav.dashboard}>
      <Card>
        <p className="text-muted">{tr.placeholder.phase.replace('{phase}', '1')}</p>
      </Card>
    </PageFrame>
  )
}
