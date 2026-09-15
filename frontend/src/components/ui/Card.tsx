import type { ReactNode } from 'react'

export function Card({
  title,
  children,
  className = '',
}: {
  title?: string
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-sm border border-border bg-surface ${className}`}>
      {title ? (
        <header className="border-b border-border px-3 py-1.5 text-xs uppercase tracking-wide text-muted">
          {title}
        </header>
      ) : null}
      <div className="p-3">{children}</div>
    </section>
  )
}
