import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { Providers } from '@/app/providers'
import { routes } from '@/app/router'
import {
  candles,
  health,
  levels,
  marketState,
  mockApi,
  predictionPage,
  signals,
} from '@/test/mockApi'

afterEach(() => vi.unstubAllGlobals())

function renderCoin(path = '/coin/BTCUSDT') {
  mockApi({
    '/health': health,
    '/symbols': { symbols: ['BTCUSDT'], timezone: 'Europe/Istanbul' },
    '/candles': candles,
    '/levels': levels,
    '/signals/': signals,
    '/predictions': predictionPage,
    '/market/BTCUSDT': marketState,
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <Providers live={false} client={client}>
      <RouterProvider router={router} />
    </Providers>,
  )
}

describe('Coin detay ekranı', () => {
  it('seçili ufkun raporunu ve modül kırılımını gösterir', async () => {
    renderCoin()

    expect(await screen.findByText(/Yukarı olasılığı %68/)).toBeInTheDocument()
    expect(screen.getByText(/teknik: EMA dizilimi yukarı yönlü/)).toBeInTheDocument()
    expect(screen.getByText(/Beni yanıltacak şey/)).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'teknik' })).toBeInTheDocument()
  })

  it('veri vermeyen modülleri ve düşük güveni saklamaz', async () => {
    renderCoin()

    expect(await screen.findByText(/güven düşük/i)).toBeInTheDocument()
    expect(screen.getByText(/orderflow/)).toBeInTheDocument()
    expect(screen.getByText(/yalnızca teknik modül/)).toBeInTheDocument()
  })

  it('tahmini olmayan ufka geçilince bunu açıkça söyler', async () => {
    renderCoin()
    const tabs = await screen.findByRole('tablist', { name: 'ufuk' })

    fireEvent.click(within(tabs).getByRole('tab', { name: '4 saat' }))

    expect(await screen.findByText(/henüz canlı tahmin yok/)).toBeInTheDocument()
  })

  it('mekanik seviyeleri ve hacim profilini listeler', async () => {
    renderCoin()

    expect(await screen.findByText(/en çok işlem gören fiyat/)).toBeInTheDocument()
    expect(screen.getByText('direnç')).toBeInTheDocument()
    expect(screen.getByText('destek')).toBeInTheDocument()
  })

  it('seviyeyi geçmişine göre değil, fiyata göre adlandırır', async () => {
    // 62.400 swing LOW'dur ama fiyat (63.000) üstündeyse bugün destektir; 63.500 dirençtir.
    renderCoin()
    const rows = await screen.findAllByRole('row')
    const low = rows.find((row) => row.textContent?.includes('62.400'))
    const high = rows.find((row) => row.textContent?.includes('63.500'))
    expect(low?.textContent).toContain('destek')
    expect(high?.textContent).toContain('direnç')
  })

  it('sembolsüz açılınca ilk coine yönlendirir', async () => {
    renderCoin('/coin')
    // Yönlendirme sonrası BTCUSDT ekranı gelir: rapor başlığı görünür.
    expect(await screen.findByText(/Yukarı olasılığı %68/)).toBeInTheDocument()
  })
})
