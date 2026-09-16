import type { ReactNode } from 'react'

/**
 * Panel içi "etiket — değer" satırı. Türev panellerinin hepsi aynı hizada okunsun diye
 * tek yerden gelir; değer sütunu mono ve sağa yaslıdır.
 */
export function MetricRow({
  label,
  value,
  tone = 'text',
  title,
}: {
  label: string
  value: ReactNode
  tone?: 'text' | 'up' | 'down' | 'muted'
  title?: string
}) {
  const toneClass = {
    text: 'text-text',
    up: 'text-up',
    down: 'text-down',
    muted: 'text-muted',
  }[tone]
  return (
    <div className="flex items-baseline justify-between gap-2 text-sm" title={title}>
      <span className="text-muted">{label}</span>
      <span className={`num ${toneClass}`}>{value}</span>
    </div>
  )
}
