import { create } from 'zustand'
import type { LivePrice } from '@/api/types'

interface PriceState {
  prices: Record<string, LivePrice>
  setPrice: (symbol: string, price: LivePrice) => void
}

export const usePriceStore = create<PriceState>((set) => ({
  prices: {},
  setPrice: (symbol, price) => set((state) => ({ prices: { ...state.prices, [symbol]: price } })),
}))

export function useLivePrice(symbol: string): LivePrice | undefined {
  return usePriceStore((state) => state.prices[symbol])
}
