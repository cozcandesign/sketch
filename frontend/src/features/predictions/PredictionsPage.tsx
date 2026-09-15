import { PageFrame } from '@/components/ui/PageFrame'
import { Card } from '@/components/ui/Card'
import { tr } from '@/i18n/tr'

export function PredictionsPage() {
  return (
    <PageFrame title={tr.nav.predictions}>
      <Card>
        <p className="text-muted">{tr.placeholder.phase.replace('{phase}', '1')}</p>
      </Card>
    </PageFrame>
  )
}
