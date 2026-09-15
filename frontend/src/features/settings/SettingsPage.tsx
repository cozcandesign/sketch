import { PageFrame } from '@/components/ui/PageFrame'
import { Card } from '@/components/ui/Card'
import { tr } from '@/i18n/tr'

export function SettingsPage() {
  return (
    <PageFrame title={tr.nav.settings}>
      <Card>
        <p className="text-muted">{tr.placeholder.phase.replace('{phase}', '6')}</p>
      </Card>
    </PageFrame>
  )
}
