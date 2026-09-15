import type { DotTone } from '@/components/ui/Dot'
import type { ConfidenceLabel } from '@/api/types'
import { tr } from '@/i18n/tr'

export const confidenceTone: Record<ConfidenceLabel, DotTone> = {
  low: 'muted',
  mid: 'info',
  high: 'up',
}

export function confidenceLabelTr(label: ConfidenceLabel): string {
  return tr.confidence[label]
}
