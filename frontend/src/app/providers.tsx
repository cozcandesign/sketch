import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useLiveConnection } from '@/api/useLive'
import { useSymbols } from '@/api/queries/market'

function LiveConnection() {
  const { data } = useSymbols()
  useLiveConnection(data?.symbols ? [...data.symbols] : [])
  return null
}

export function Providers({
  children,
  live = true,
  client,
}: {
  children: ReactNode
  live?: boolean
  client?: QueryClient
}) {
  const [queryClient] = useState(
    () =>
      client ??
      new QueryClient({
        defaultOptions: { queries: { retry: 1, staleTime: 5_000, refetchOnWindowFocus: true } },
      }),
  )
  return (
    <QueryClientProvider client={queryClient}>
      {live ? <LiveConnection /> : null}
      {children}
    </QueryClientProvider>
  )
}
