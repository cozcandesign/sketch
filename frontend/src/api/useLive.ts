import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getWsClient, isTopicMessage } from '@/api/ws'
import { healthKeys } from '@/api/queries/health'
import { marketKeys } from '@/api/queries/market'
import { useUiStore } from '@/store/ui'
import { usePriceStore } from '@/store/prices'
import type { LivePrice } from '@/api/types'

const BASE_TOPICS = ['health', 'predictions', 'outcomes']

// Canlı bağlantı: WS mesajları store ve query cache'ini tazeler; bileşenler yalnızca useQuery görür.
export function useLiveConnection(symbols: string[] = []): void {
  const queryClient = useQueryClient()
  const setWsStatus = useUiStore((s) => s.setWsStatus)
  const setLastWsMessageAt = useUiStore((s) => s.setLastWsMessageAt)
  const setPrice = usePriceStore((s) => s.setPrice)

  useEffect(() => {
    const client = getWsClient()
    const offStatus = client.onStatus(setWsStatus)
    const offMessage = client.onMessage((msg) => {
      setLastWsMessageAt(new Date())
      if (!isTopicMessage(msg)) return
      if (msg.topic === 'health') {
        void queryClient.invalidateQueries({ queryKey: healthKeys.all })
        return
      }
      if (msg.topic.startsWith('price.')) {
        const symbol = msg.topic.slice('price.'.length)
        setPrice(symbol, msg.data as LivePrice)
        return
      }
      if (msg.topic === 'predictions' || msg.topic === 'outcomes') {
        void queryClient.invalidateQueries({ queryKey: ['predictions'] })
        void queryClient.invalidateQueries({ queryKey: ['calibration'] })
        void queryClient.invalidateQueries({ queryKey: marketKeys.symbols.slice(0, 0) })
        void queryClient.invalidateQueries({ queryKey: ['market'] })
      }
    })
    client.subscribe(BASE_TOPICS)
    client.connect()
    return () => {
      offStatus()
      offMessage()
      // Soket uygulama ömrü boyunca açık kalır (StrictMode çift mount'ta yeniden bağlanma olmasın).
    }
  }, [queryClient, setWsStatus, setLastWsMessageAt, setPrice])

  useEffect(() => {
    if (symbols.length === 0) return
    const client = getWsClient()
    const topics = symbols.map((symbol) => `price.${symbol}`)
    client.subscribe(topics)
    return () => client.unsubscribe(topics)
  }, [symbols])
}
