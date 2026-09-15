import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { Providers } from '@/app/providers'
import { PredictionsPage } from '@/features/predictions/PredictionsPage'
import { mockApi, predictionPage } from '@/test/mockApi'

afterEach(() => vi.unstubAllGlobals())

function renderPage(page = predictionPage) {
  mockApi({
    '/symbols': { symbols: ['BTCUSDT'], timezone: 'Europe/Istanbul' },
    '/predictions': page,
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <Providers live={false} client={client}>
      <PredictionsPage />
    </Providers>,
  )
}

describe('PredictionsPage', () => {
  it('lists predictions with outcome and hit columns', async () => {
    renderPage()
    expect(await screen.findByText('Referans: taban oranı')).toBeInTheDocument()
    expect(screen.getByText('%70')).toBeInTheDocument()
    // "isabet" hem sütun başlığı hem de rozet metnidir
    expect(screen.getAllByText('isabet').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('0,090')).toBeInTheDocument()
  })

  it('shows an empty state when there are no predictions', async () => {
    renderPage({ items: [], next_cursor: null })
    expect(await screen.findByText(/Henüz tahmin yok/)).toBeInTheDocument()
  })
})
