const LABELS: Record<string, string> = {
  'baseline-climatology-1': 'Referans: taban oranı',
  'baseline-momentum-1': 'Referans: son mum rengi',
}

/** Tahminciyi okunur ada çevirir; bilinmeyen sürüm olduğu gibi gösterilir. */
export function modelLabel(version: string): string {
  return LABELS[version] ?? version
}
