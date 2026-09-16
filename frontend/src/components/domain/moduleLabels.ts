// Modül ve alt bileşen adlarının Türkçe karşılıkları (JSX'te çıplak string olmasın diye ayrı dosya).
import { tr } from '@/i18n/tr'

export function moduleLabel(name: string): string {
  return tr.modules[name as keyof typeof tr.modules] ?? name
}

export function componentLabel(name: string): string {
  return tr.components[name as keyof typeof tr.components] ?? name
}
