// Sayı biçimleri tek yerden (CLAUDE.md §7).

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
