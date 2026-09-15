import { useQuery } from '@tanstack/react-query'
import { apiGet } from '@/api/client'
import type { Calibration } from '@/api/types'

export type CalibrationWindow = '7d' | '30d' | '90d' | 'all'

export const calibrationKeys = {
  all: (window: CalibrationWindow, symbol?: string, horizon?: string) =>
    ['calibration', window, symbol ?? null, horizon ?? null] as const,
}

export function useCalibration(window: CalibrationWindow, symbol?: string, horizon?: string) {
  return useQuery({
    queryKey: calibrationKeys.all(window, symbol, horizon),
    queryFn: () => {
      const params = new URLSearchParams({ window })
      if (symbol) params.set('symbol', symbol)
      if (horizon) params.set('horizon', horizon)
      return apiGet<Calibration>(`/calibration?${params.toString()}`)
    },
    refetchInterval: 120_000,
  })
}
