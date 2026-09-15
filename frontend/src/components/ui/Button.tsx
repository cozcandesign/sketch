import type { ReactNode } from 'react'

export function Button({
  children,
  onClick,
  disabled = false,
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-sm border border-border bg-surface-2 px-2 py-1 text-sm text-text hover:border-accent disabled:cursor-not-allowed disabled:text-muted"
    >
      {children}
    </button>
  )
}
