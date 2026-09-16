import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/api/client'
import type { Orderflow } from '@/api/types'

export const orderflowKeys = {
  orderflow: (symbol: string, minutes: number) => ['orderflow', symbol, minutes] as const,
}

/** Coin ekranının türev panelleri: dakika serisi, zorunlu kapatmalar, funding, OI, long/short. */
export function useOrderflow(symbol: string, minutes: number) {
  return useQuery({
    queryKey: orderflowKeys.orderflow(symbol, minutes),
    queryFn: () => apiGet<Orderflow>(`/market/${symbol}/orderflow?minutes=${minutes}`),
    refetchInterval: 60_000,
  })
}
