import type { ReactNode } from 'react'
import type { DotTone } from '@/components/ui/Dot'

const toneClass: Record<DotTone, string> = {
  up: 'text-up border-up/40',
  down: 'text-down border-down/40',
  neutral: 'text-neutral border-border',
  warn: 'text-warn border-warn/40',
  critical: 'text-critical border-critical/40',
  info: 'text-info border-info/40',
  muted: 'text-muted border-border',
}

export function Badge({ tone = 'neutral', children }: { tone?: DotTone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-xs uppercase tracking-wide ${toneClass[tone]}`}
    >
      {children}
    </span>
  )
}
