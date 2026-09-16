import { tr } from '@/i18n/tr'

/** Gerekçe maddeleri. Sıra katkı büyüklüğüne göre backend'den gelir; burada yeniden sıralanmaz. */
export function RationaleList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted">{tr.coin.noRationale}</p>
  }
  return (
    <ul className="flex list-disc flex-col gap-1 pl-4 text-sm">
      {items.map((text, index) => (
        <li key={index}>{text}</li>
      ))}
    </ul>
  )
}
