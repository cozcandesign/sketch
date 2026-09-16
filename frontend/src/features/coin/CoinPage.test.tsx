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
  orderflow,
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
    '/orderflow': orderflow,
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
    // Eksik modüller Türkçe adlarıyla listelenir, kod adlarıyla değil.
    expect(screen.getByText(/haber, makro, duyarlılık/)).toBeInTheDocument()
    expect(screen.getByText(/2\/5 modül veri veriyor \(teknik, order flow\)/)).toBeInTheDocument()
  })

  it('order flow panellerini ve dinlenen süreyi gösterir', async () => {
    renderCoin()

    expect(await screen.findByText('Funding')).toBeInTheDocument()
    expect(screen.getByText('Açık pozisyon')).toBeInTheDocument()
    expect(screen.getByText('Zorunlu kapatmalar')).toBeInTheDocument()
    expect(screen.getByText('Order book')).toBeInTheDocument()
    expect(screen.getByText(/Kümülatif hacim farkı/)).toBeInTheDocument()
    // Kapsama rozeti her zaman görünür: kesinti olduğunda kullanıcı bunu görmeli (K22).
    expect(screen.getByText(/dinlenen süre %99/)).toBeInTheDocument()
  })

  it('order flow bileşenlerini modül kırılımında Türkçe adlandırır', async () => {
    renderCoin()

    expect(await screen.findByRole('meter', { name: 'order flow' })).toBeInTheDocument()
    expect(screen.getByText('açık pozisyon + fiyat')).toBeInTheDocument()
    expect(screen.getByText('agresif akış (CVD)')).toBeInTheDocument()
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
