import { Badge } from '@/components/ui/Badge'
import { confidenceLabelTr, confidenceTone } from '@/components/domain/confidence'
import type { ConfidenceLabel } from '@/api/types'
import { tr } from '@/i18n/tr'

export function ConfidenceBadge({ label }: { label: ConfidenceLabel }) {
  return (
    <Badge tone={confidenceTone[label]}>
      {tr.confidence.label} {confidenceLabelTr(label)}
    </Badge>
  )
}
