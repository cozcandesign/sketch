import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getWsClient, isTopicMessage } from '@/api/ws'
import { healthKeys } from '@/api/queries/health'
import { useUiStore } from '@/store/ui'

// Canlı bağlantı: WS mesajları query cache'ini tazeler; bileşenler yalnızca useQuery görür.
export function useLiveConnection(): void {
  const queryClient = useQueryClient()
  const setWsStatus = useUiStore((s) => s.setWsStatus)
  const setLastWsMessageAt = useUiStore((s) => s.setLastWsMessageAt)

  useEffect(() => {
    const client = getWsClient()
    const offStatus = client.onStatus(setWsStatus)
    const offMessage = client.onMessage((msg) => {
      setLastWsMessageAt(new Date())
      if (isTopicMessage(msg) && msg.topic === 'health') {
        void queryClient.invalidateQueries({ queryKey: healthKeys.all })
      }
    })
    client.subscribe(['health'])
    client.connect()
    return () => {
      offStatus()
      offMessage()
      // Soket uygulama ömrü boyunca açık kalır (StrictMode çift mount'ta yeniden bağlanma olmasın).
    }
  }, [queryClient, setWsStatus, setLastWsMessageAt])
}
