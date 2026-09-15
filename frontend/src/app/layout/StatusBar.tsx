import { useHealth } from '@/api/queries/health'
import { Badge } from '@/components/ui/Badge'
import { formatBytes, formatSeconds } from '@/lib/format'
import { formatTime } from '@/lib/time'
import { FRONTEND_GIT_SHA, isVersionMismatch } from '@/lib/build'
import { useUiStore } from '@/store/ui'
import { tr } from '@/i18n/tr'

export function StatusBar() {
  const { data } = useHealth()
  const lastWsMessageAt = useUiStore((s) => s.lastWsMessageAt)
  const backendSha = data?.build.git_sha
  const mismatch = isVersionMismatch(FRONTEND_GIT_SHA, backendSha)

  return (
    <footer className="flex h-row items-center gap-4 border-t border-border bg-surface px-3 text-xs text-muted">
      <span>
        {tr.common.ui} {tr.common.commit} <span className="num text-text">{FRONTEND_GIT_SHA}</span>
      </span>
      <span>
        API {tr.common.commit} <span className="num text-text">{backendSha ?? tr.common.none}</span>
      </span>
      {mismatch ? (
        <span title={tr.common.versionMismatchHint}>
          <Badge tone="warn">{tr.common.versionMismatch}</Badge>
        </span>
      ) : null}
      <span>
        API {tr.common.version} <span className="num">{data?.api_version ?? tr.common.none}</span>
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
