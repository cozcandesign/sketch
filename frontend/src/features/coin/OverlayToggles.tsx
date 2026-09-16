import { tr } from '@/i18n/tr'

export interface Overlays {
  ema: boolean
  levels: boolean
  profile: boolean
}

/** Grafik üstü katmanlar. Varsayılan açık; kullanıcı gürültü bulursa kapatır. */
export function OverlayToggles({
  value,
  onChange,
}: {
  value: Overlays
  onChange: (next: Overlays) => void
}) {
  const items: { key: keyof Overlays; label: string }[] = [
    { key: 'ema', label: tr.coin.overlays.ema },
    { key: 'levels', label: tr.coin.overlays.levels },
    { key: 'profile', label: tr.coin.overlays.profile },
  ]
  return (
    <div className="flex items-center gap-2">
      {items.map((item) => (
        <label key={item.key} className="flex items-center gap-1 text-xs text-muted">
          <input
            type="checkbox"
            checked={value[item.key]}
            onChange={(event) => onChange({ ...value, [item.key]: event.target.checked })}
            className="accent-accent"
          />
          <span>{item.label}</span>
        </label>
      ))}
    </div>
  )
}
