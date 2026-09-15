import type { DotTone } from '@/components/ui/Dot'
import type { HealthStatus } from '@/api/types'
import { tr } from '@/i18n/tr'

export const healthTone: Record<HealthStatus, DotTone> = {
  ok: 'up',
  degraded: 'warn',
  down: 'critical',
  disabled: 'muted',
  budget_exhausted: 'info',
}

export function healthLabel(status: HealthStatus): string {
  return tr.status.health[status]
}
