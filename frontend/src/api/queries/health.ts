import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/api/client'
import type { HealthResponse } from '@/api/types'

export const healthKeys = { all: ['health'] as const }

export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health')
}

export function useHealth() {
  return useQuery({ queryKey: healthKeys.all, queryFn: fetchHealth, refetchInterval: 15_000 })
}
