import { formatScore } from '@/lib/format'

/**
 * −1..+1 arası bir skoru merkezden yayılan çubukla gösterir.
 * Renk yalnızca yönü anlatır; sayı her zaman yazılıdır (renk körlüğü için).
 */
export function ScoreBar({
  label,
  score,
  hint,
  muted = false,
}: {
  label: string
  score: number
  hint?: string
  muted?: boolean
}) {
  const width = Math.min(50, Math.abs(score) * 50)
  const tone = muted
    ? 'bg-neutral'
    : score > 0.02
      ? 'bg-up'
      : score < -0.02
        ? 'bg-down'
        : 'bg-neutral'
  const textTone = muted
    ? 'text-muted'
    : score > 0.02
      ? 'text-up'
      : score < -0.02
        ? 'text-down'
        : 'text-neutral'

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-muted">{label}</span>
        <span className={`num text-xs ${textTone}`}>{formatScore(score, 2)}</span>
      </div>
      <div
        className="relative h-1.5 w-full rounded-sm bg-surface-2"
        role="meter"
        aria-valuenow={Number(score.toFixed(2))}
        aria-valuemin={-1}
        aria-valuemax={1}
        aria-label={label}
      >
        <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
        <span
          className={`absolute inset-y-0 rounded-sm ${tone}`}
          style={
            score < 0 ? { right: '50%', width: `${width}%` } : { left: '50%', width: `${width}%` }
          }
        />
      </div>
      {hint ? <span className="text-xs text-muted">{hint}</span> : null}
    </div>
  )
}
