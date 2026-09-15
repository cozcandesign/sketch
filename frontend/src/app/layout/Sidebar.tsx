import { NavLink } from 'react-router'
import { NAV_ITEMS } from '@/app/layout/nav'
import { tr } from '@/i18n/tr'

export function Sidebar() {
  return (
    <nav className="flex flex-col border-r border-border bg-surface" aria-label="Ana menü">
      <div className="border-b border-border px-3 py-2">
        <div className="text-sm font-semibold tracking-wide">{tr.app.name}</div>
        <div className="text-xs text-muted">{tr.app.tagline}</div>
      </div>
      <ul className="flex flex-col py-1">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center justify-between px-3 text-sm h-row ${
                  isActive
                    ? 'bg-surface-2 text-text'
                    : 'text-muted hover:bg-surface-2 hover:text-text'
                }`
              }
            >
              <span>{item.label}</span>
              <kbd className="num rounded-sm border border-border px-1 text-xs text-muted">
                {item.key}
              </kbd>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
