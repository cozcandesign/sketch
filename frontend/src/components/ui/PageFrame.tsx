import type { ReactNode } from 'react'

export function PageFrame({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  )
}
