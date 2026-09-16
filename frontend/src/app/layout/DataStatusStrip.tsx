import { useHealth } from '@/api/queries/health'
import { DataHealthDot } from '@/components/domain/DataHealthDot'
import { healthLabel } from '@/components/domain/healthStatus'
import { Dot } from '@/components/ui/Dot'
import { relativeTime } from '@/lib/time'
import { useNow } from '@/lib/useNow'
import { tr } from '@/i18n/tr'

// Her ekranın üstünde (K22): hangi collector çalışıyor, son güncelleme, hangisi kopuk.
export function DataStatusStrip() {
  const { data, isError } = useHealth()
  const now = useNow()
  const labels = { never: tr.status.never }

  return (
    <div
      // Kaydırma yerine satır kaydırma: ekrana sığmayan bir "kopuk" uyarısı görünmez olurdu (K22).
      className="flex min-h-row flex-wrap items-center gap-x-3 gap-y-0.5 border-b border-border bg-surface-2 px-3 py-0.5 text-xs"
      role="status"
      aria-label="Veri durumu"
    >
      <span className="flex items-center gap-1.5">
        <Dot
          tone={isError ? 'critical' : data?.engine.alive ? 'up' : 'critical'}
          title={data?.engine.alive ? tr.status.engineAlive : tr.status.engineStale}
        />
        <span className="text-muted">engine</span>
        <span>
          {isError
            ? tr.common.error
            : data == null
              ? tr.status.engineUnknown
              : data.engine.alive
                ? tr.status.engineAlive
                : tr.status.engineStale}
        </span>
        {data?.engine.last_heartbeat ? (
          <span className="num text-muted">
            {relativeTime(data.engine.last_heartbeat, now, labels)}
          </span>
        ) : null}
      </span>
      <span className="h-3 w-px bg-border" />
      <span className="flex items-center gap-1.5">
        <Dot tone={data?.live_prices.connected ? 'up' : 'critical'} />
        <span>{tr.status.livePrices}</span>
        <span className="text-muted">
          {data?.live_prices.connected ? tr.status.connected : tr.status.disconnected}
        </span>
        {data?.live_prices.last_message_at ? (
          <span className="num text-muted">
            {relativeTime(data.live_prices.last_message_at, now, labels)}
          </span>
        ) : null}
      </span>
      <span className="h-3 w-px bg-border" />
      {data && data.collectors.length === 0 ? (
        <span className="text-muted">{tr.status.noCollectors}</span>
      ) : null}
      {data?.collectors.map((c) => (
        <span
          key={c.collector}
          className="flex items-center gap-1.5 whitespace-nowrap"
          title={c.last_error ?? undefined}
        >
          <DataHealthDot status={c.status} />
          <span>{c.collector}</span>
          <span className="text-muted">{healthLabel(c.status)}</span>
          <span className="num text-muted">{relativeTime(c.last_success_at, now, labels)}</span>
          {c.status === 'down' && c.last_error ? (
            <span className="max-w-64 truncate text-critical" title={c.last_error}>
              {c.last_error}
            </span>
          ) : null}
        </span>
      ))}
    </div>
  )
}
