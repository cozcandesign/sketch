import { Dot } from '@/components/ui/Dot'
import { healthLabel, healthTone } from '@/components/domain/healthStatus'
import type { HealthStatus } from '@/api/types'

export function DataHealthDot({ status }: { status: HealthStatus }) {
  return <Dot tone={healthTone[status]} title={healthLabel(status)} />
}
