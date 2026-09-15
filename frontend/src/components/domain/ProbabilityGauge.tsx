import { formatProbability } from '@/lib/format'
import { tr } from '@/i18n/tr'

/** %50'yi merkez alan yatay ölçek. Renk yalnızca yönü anlatır; sayı her zaman yazılıdır. */
export function ProbabilityGauge({
  pUp,
  label,
  compact = false,
}: {
  pUp: number
  label?: string
  compact?: boolean
}) {
  const deviation = pUp - 0.5
  const direction = deviation > 0.02 ? 'up' : deviation < -0.02 ? 'down' : 'neutral'
  const widthPct = Math.min(50, Math.abs(deviation) * 100)
  const barColor = direction === 'up' ? 'bg-up' : direction === 'down' ? 'bg-down' : 'bg-neutral'
  const textColor =
    direction === 'up' ? 'text-up' : direction === 'down' ? 'text-down' : 'text-neutral'

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-baseline justify-between gap-2">
        {label ? <span className="text-xs text-muted">{label}</span> : null}
        <span className={`num ${compact ? 'text-sm' : 'text-lg'} ${textColor}`}>
          {formatProbability(pUp)}
        </span>
      </div>
      <div
        className="relative h-1.5 w-full rounded-sm bg-surface-2"
        role="meter"
        aria-valuenow={Math.round(pUp * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${tr.dashboard.horizonHeader} ${formatProbability(pUp)}`}
      >
        <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
        <span
          className={`absolute inset-y-0 ${barColor} rounded-sm`}
          style={
            direction === 'down'
              ? { right: '50%', width: `${widthPct}%` }
              : { left: '50%', width: `${widthPct}%` }
          }
        />
      </div>
    </div>
  )
}
