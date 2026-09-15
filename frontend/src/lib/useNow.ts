import { useEffect, useState } from 'react'

/** Göreli zaman etiketlerinin tazelenmesi için periyodik "şimdi". */
export function useNow(intervalMs = 1_000): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}
