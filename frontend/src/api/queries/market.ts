import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/api/client'
import type { Candles, MarketState, SymbolsResponse } from '@/api/types'

export const marketKeys = {
  symbols: ['symbols'] as const,
  state: (symbol: string) => ['market', symbol] as const,
  candles: (symbol: string, interval: string, limit: number) =>
    ['market', symbol, 'candles', interval, limit] as const,
}

export function useSymbols() {
  return useQuery({
    queryKey: marketKeys.symbols,
    queryFn: () => apiGet<SymbolsResponse>('/symbols'),
    staleTime: 60_000,
  })
}

export function useMarket(symbol: string) {
  return useQuery({
    queryKey: marketKeys.state(symbol),
    queryFn: () => apiGet<MarketState>(`/market/${symbol}`),
    refetchInterval: 30_000,
  })
}

export function useCandles(symbol: string, interval: string, limit = 300) {
  return useQuery({
    queryKey: marketKeys.candles(symbol, interval, limit),
    queryFn: () => apiGet<Candles>(`/market/${symbol}/candles?interval=${interval}&limit=${limit}`),
    refetchInterval: 60_000,
  })
}
