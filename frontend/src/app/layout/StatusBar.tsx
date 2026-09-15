import { useHealth } from '@/api/queries/health'
import { formatBytes, formatSeconds } from '@/lib/format'
import { formatTime } from '@/lib/time'
import { useUiStore } from '@/store/ui'
import { tr } from '@/i18n/tr'

export function StatusBar() {
  const { data } = useHealth()
  const lastWsMessageAt = useUiStore((s) => s.lastWsMessageAt)
  return (
    <footer className="flex h-row items-center gap-4 border-t border-border bg-surface px-3 text-xs text-muted">
      <span>
        API {tr.common.version} <span className="num">{data?.api_version ?? '—'}</span>
      </span>
      <span>
        engine {tr.common.version} <span className="num">{data?.engine.version ?? '—'}</span>
      </span>
      <span>
        heartbeat <span className="num">{formatSeconds(data?.engine.age_seconds)}</span>
      </span>
      <span>
        DB <span className="num">{formatBytes(data?.db.size_bytes)}</span>
      </span>
      <span>
        WS {tr.status.lastUpdate}{' '}
        <span className="num">
          {lastWsMessageAt ? formatTime(lastWsMessageAt) : tr.status.never}
        </span>
      </span>
      <span className="ml-auto">
        {data?.server_time ? <span className="num">{formatTime(data.server_time)}</span> : null}
      </span>
    </footer>
  )
}
