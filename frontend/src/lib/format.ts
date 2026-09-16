// Sayı biçimleri tek yerden (CLAUDE.md §7).

const priceFormatter = new Intl.NumberFormat('tr-TR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const smallPriceFormatter = new Intl.NumberFormat('tr-TR', {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
})

export function formatPrice(value: number | null | undefined): string {
  if (value == null) return '—'
  return value >= 10 ? priceFormatter.format(value) : smallPriceFormatter.format(value)
}

/** Oranı yüzdeye çevirir: 0.0123 → "+%1,23" */
export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value == null) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}%${(value * 100).toFixed(digits).replace('.', ',')}`
}

/** Olasılığı tam sayı yüzde olarak: 0.62 → "%62" */
export function formatProbability(value: number | null | undefined): string {
  if (value == null) return '—'
  return `%${Math.round(value * 100)}`
}

export function formatScore(value: number | null | undefined, digits = 3): string {
  if (value == null) return '—'
  return value.toFixed(digits).replace('.', ',')
}

export function formatCount(value: number | null | undefined): string {
  if (value == null) return '—'
  return new Intl.NumberFormat('tr-TR').format(value)
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.round(seconds)} sn`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} dk`
  return `${(seconds / 3600).toFixed(1)} sa`
}

/**
 * Büyük USD tutarlarını kısaltır: 1.250.000 → "1,25 Mn $". Likidasyon ve açık pozisyon
 * panellerinde tam basamak okunmaz; büyüklük sırası okunur.
 */
export function formatUsdCompact(value: number | null | undefined): string {
  if (value == null) return '—'
  const sign = value < 0 ? '-' : ''
  const abs = Math.abs(value)
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2).replace('.', ',')} Mr $`
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2).replace('.', ',')} Mn $`
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1).replace('.', ',')} B $`
  return `${sign}${abs.toFixed(0)} $`
}
