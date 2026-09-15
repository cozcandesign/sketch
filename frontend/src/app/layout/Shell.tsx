import { Outlet } from 'react-router'
import { Sidebar } from '@/app/layout/Sidebar'
import { Topbar } from '@/app/layout/Topbar'
import { DataStatusStrip } from '@/app/layout/DataStatusStrip'
import { StatusBar } from '@/app/layout/StatusBar'

export function Shell() {
  return (
    <div className="grid h-full grid-cols-[var(--mp-sidebar-w)_1fr] bg-bg text-text">
      <Sidebar />
      <div className="flex min-w-0 flex-col">
        <Topbar />
        <DataStatusStrip />
        <main className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
        <StatusBar />
      </div>
    </div>
  )
}
