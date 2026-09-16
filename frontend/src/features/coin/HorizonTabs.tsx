import type { HorizonKey } from '@/api/types'
import { tr } from '@/i18n/tr'

/** Ufuk sekmeleri. Seçim yalnızca görünümü değiştirir; veri her ufuk için zaten yüklüdür. */
export function HorizonTabs({
  value,
  onChange,
  horizons,
  labels,
}: {
  value: HorizonKey
  onChange: (horizon: HorizonKey) => void
  horizons: readonly HorizonKey[]
  labels: Record<HorizonKey, string>
}) {
  return (
    <div role="tablist" aria-label={tr.coin.horizonTabs} className="flex gap-1">
      {horizons.map((horizon) => {
        const active = horizon === value
        return (
          <button
            key={horizon}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(horizon)}
            className={`rounded-sm border px-2 py-0.5 text-sm ${
              active
                ? 'border-accent text-accent'
                : 'border-border text-muted hover:border-accent/50 hover:text-text'
            }`}
          >
            {labels[horizon]}
          </button>
        )
      })}
    </div>
  )
}
