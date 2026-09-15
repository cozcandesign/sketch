import type { ReactNode } from 'react'

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  )
}

export function Th({
  children,
  align = 'left',
}: {
  children: ReactNode
  align?: 'left' | 'right'
}) {
  return (
    <th
      className={`border-b border-border px-2 py-1 text-xs font-medium tracking-wide text-muted uppercase ${
        align === 'right' ? 'text-right' : 'text-left'
      }`}
    >
      {children}
    </th>
  )
}

export function Td({
  children,
  align = 'left',
  mono = false,
}: {
  children: ReactNode
  align?: 'left' | 'right'
  mono?: boolean
}) {
  return (
    <td
      className={`border-b border-border/60 px-2 py-1 ${align === 'right' ? 'text-right' : ''} ${
        mono ? 'num' : ''
      }`}
    >
      {children}
    </td>
  )
}

export function Tr({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return (
    <tr
      onClick={onClick}
      className={onClick ? 'cursor-pointer hover:bg-surface-2' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === 'Enter') onClick()
            }
          : undefined
      }
    >
      {children}
    </tr>
  )
}
