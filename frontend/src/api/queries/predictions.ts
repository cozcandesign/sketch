import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { apiGet } from '@/api/client'
import type { Prediction, PredictionPage } from '@/api/types'

export interface PredictionFilters {
  symbol?: string
  horizon?: string
  status?: 'all' | 'active' | 'resolved'
}

export const predictionKeys = {
  list: (filters: PredictionFilters) => ['predictions', filters] as const,
  detail: (id: number) => ['predictions', id] as const,
}

function toQuery(filters: PredictionFilters, cursor?: number): string {
  const params = new URLSearchParams({ limit: '50' })
  if (filters.symbol) params.set('symbol', filters.symbol)
  if (filters.horizon) params.set('horizon', filters.horizon)
  if (filters.status && filters.status !== 'all') params.set('status', filters.status)
  if (cursor != null) params.set('cursor', String(cursor))
  return params.toString()
}

export function usePredictions(filters: PredictionFilters) {
  return useInfiniteQuery({
    queryKey: predictionKeys.list(filters),
    queryFn: ({ pageParam }) =>
      apiGet<PredictionPage>(`/predictions?${toQuery(filters, pageParam ?? undefined)}`),
    initialPageParam: null as number | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? null,
    refetchInterval: 60_000,
  })
}

export function usePrediction(id: number | null) {
  return useQuery({
    queryKey: predictionKeys.detail(id ?? -1),
    queryFn: () => apiGet<Prediction>(`/predictions/${id}`),
    enabled: id != null,
  })
}
