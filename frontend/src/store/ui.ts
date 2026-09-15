import { create } from 'zustand'
import type { WsStatus } from '@/api/ws'

interface UiState {
  wsStatus: WsStatus
  lastWsMessageAt: Date | null
  setWsStatus: (status: WsStatus) => void
  setLastWsMessageAt: (at: Date) => void
}

export const useUiStore = create<UiState>((set) => ({
  wsStatus: 'disconnected',
  lastWsMessageAt: null,
  setWsStatus: (wsStatus) => set({ wsStatus }),
  setLastWsMessageAt: (lastWsMessageAt) => set({ lastWsMessageAt }),
}))
