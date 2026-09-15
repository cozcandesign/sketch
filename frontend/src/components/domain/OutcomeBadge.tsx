import { Badge } from '@/components/ui/Badge'
import type { Outcome } from '@/api/types'
import { tr } from '@/i18n/tr'

export function OutcomeBadge({ outcome }: { outcome: Outcome | null | undefined }) {
  if (!outcome) return <Badge tone="muted">{tr.predictions.outcome.pending}</Badge>
  if (outcome.outcome === 'unresolved')
    return <Badge tone="warn">{tr.predictions.outcome.unresolved}</Badge>
  const up = outcome.outcome === 'up'
  return (
    <Badge tone={up ? 'up' : 'down'}>
      {up ? tr.predictions.outcome.up : tr.predictions.outcome.down}
    </Badge>
  )
}

export function HitBadge({ hit }: { hit: boolean | null | undefined }) {
  if (hit == null) return <span className="text-muted">{tr.common.none}</span>
  return (
    <Badge tone={hit ? 'up' : 'down'}>{hit ? tr.predictions.hit.yes : tr.predictions.hit.no}</Badge>
  )
}
