export type DotTone = 'up' | 'down' | 'neutral' | 'warn' | 'critical' | 'info' | 'muted'

const toneClass: Record<DotTone, string> = {
  up: 'bg-up',
  down: 'bg-down',
  neutral: 'bg-neutral',
  warn: 'bg-warn',
  critical: 'bg-critical',
  info: 'bg-info',
  muted: 'bg-muted',
}

export function Dot({
  tone,
  title,
  pulse = false,
}: {
  tone: DotTone
  title?: string
  pulse?: boolean
}) {
  return (
    <span
      aria-label={title}
      title={title}
      className={`inline-block size-2 rounded-full ${toneClass[tone]} ${pulse ? 'animate-pulse' : ''}`}
    />
  )
}
