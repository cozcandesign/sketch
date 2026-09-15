export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-1.5" aria-hidden>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-row rounded-sm bg-surface-2" />
      ))}
    </div>
  )
}
