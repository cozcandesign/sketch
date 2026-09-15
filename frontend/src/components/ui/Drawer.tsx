import type { ReactNode } from 'react'
import { Button } from '@/components/ui/Button'

export function Drawer({
  title,
  open,
  onClose,
  closeLabel,
  children,
}: {
  title: string
  open: boolean
  onClose: () => void
  closeLabel: string
  children: ReactNode
}) {
  if (!open) return null
  return (
    <aside
      className="fixed top-0 right-0 z-20 flex h-full w-[min(560px,90vw)] flex-col border-l border-border bg-surface shadow-xl"
      role="dialog"
      aria-label={title}
    >
      <header className="flex items-center justify-between border-b border-border px-3 py-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        <Button onClick={onClose}>{closeLabel}</Button>
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-3">{children}</div>
    </aside>
  )
}
