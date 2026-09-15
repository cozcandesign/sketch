import { Badge } from '@/components/ui/Badge'
import { Dot, type DotTone } from '@/components/ui/Dot'
import { useUiStore } from '@/store/ui'
import { tr } from '@/i18n/tr'
import type { WsStatus } from '@/api/ws'

const wsTone: Record<WsStatus, DotTone> = {
  connected: 'up',
  connecting: 'warn',
  disconnected: 'critical',
}
const wsLabel: Record<WsStatus, string> = {
  connected: tr.status.connected,
  connecting: tr.status.connecting,
  disconnected: tr.status.disconnected,
}

export function Topbar() {
  const wsStatus = useUiStore((s) => s.wsStatus)
  return (
    <header className="flex h-row items-center justify-between border-b border-border bg-surface px-3">
      <div className="text-xs text-muted">{tr.app.tagline}</div>
      <Badge tone={wsTone[wsStatus]}>
        <Dot tone={wsTone[wsStatus]} pulse={wsStatus === 'connecting'} />
        <span>WS {wsLabel[wsStatus]}</span>
      </Badge>
    </header>
  )
}
