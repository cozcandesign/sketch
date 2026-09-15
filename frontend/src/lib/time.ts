// Zaman gösterimi tek yerden (CLAUDE.md §7). Sunucu UTC gönderir; burada yerel saate çevrilir.

export type RelativeLabels = { never: string }

const SEC = 1_000
const MIN = 60 * SEC
const HOUR = 60 * MIN
const DAY = 24 * HOUR

/** "12 sn önce", "3 dk önce", "2 sa önce", "4 g önce"; null → labels.never. */
export function relativeTime(
  iso: string | Date | null | undefined,
  now: Date,
  labels: RelativeLabels,
): string {
  if (!iso) return labels.never
  const then = typeof iso === 'string' ? new Date(iso) : iso
  const diff = Math.max(0, now.getTime() - then.getTime())
  if (diff < MIN) return `${Math.floor(diff / SEC)} sn önce`
  if (diff < HOUR) return `${Math.floor(diff / MIN)} dk önce`
  if (diff < DAY) return `${Math.floor(diff / HOUR)} sa önce`
  return `${Math.floor(diff / DAY)} g önce`
}

/** Saniye cinsinden yaş; null güvenli. */
export function ageSeconds(iso: string | null | undefined, now: Date): number | null {
  if (!iso) return null
  return Math.max(0, (now.getTime() - new Date(iso).getTime()) / SEC)
}

export function formatDateTime(iso: string | Date, timeZone = 'Europe/Istanbul'): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso
  return new Intl.DateTimeFormat('tr-TR', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(d)
}

export function formatTime(iso: string | Date, timeZone = 'Europe/Istanbul'): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso
  return new Intl.DateTimeFormat('tr-TR', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(d)
}
