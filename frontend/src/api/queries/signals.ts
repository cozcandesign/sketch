import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/api/client'
import type { Levels, Signals } from '@/api/types'

export const signalKeys = {
  signals: (symbol: string) => ['signals', symbol] as const,
  levels: (symbol: string, interval: string) => ['levels', symbol, interval] as const,
}

/** Her ufkun son canlı tahmini ve onu üreten modül skorları. */
export function useSignals(symbol: string) {
  return useQuery({
    queryKey: signalKeys.signals(symbol),
    queryFn: () => apiGet<Signals>(`/signals/${symbol}`),
    refetchInterval: 60_000,
  })
}

/** Grafik üstü mekanik destek/direnç ve hacim profili. */
export function useLevels(symbol: string, interval: string) {
  return useQuery({
    queryKey: signalKeys.levels(symbol, interval),
    queryFn: () => apiGet<Levels>(`/market/${symbol}/levels?interval=${interval}`),
    refetchInterval: 120_000,
  })
}
