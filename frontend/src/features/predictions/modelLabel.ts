import { tr } from '@/i18n/tr'

const LABELS: Record<string, string> = {
  'baseline-climatology-1': `Referans: ${tr.dashboard.models.climatology}`,
  'baseline-momentum-1': `Referans: ${tr.dashboard.models.momentum}`,
}

/** Panelde yer dar olduğu için kısa ad. */
const SHORT_LABELS: Record<string, string> = {
  'baseline-climatology-1': tr.dashboard.models.climatology,
  'baseline-momentum-1': tr.dashboard.models.momentum,
}

export function shortModelLabel(version: string): string {
  return SHORT_LABELS[version] ?? version
}

/** Tahminciyi okunur ada çevirir; bilinmeyen sürüm olduğu gibi gösterilir. */
export function modelLabel(version: string): string {
  return LABELS[version] ?? version
}
