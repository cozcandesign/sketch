import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { QueryClient } from '@tanstack/react-query'
import { Providers } from '@/app/providers'
import { routes } from '@/app/router'

afterEach(() => vi.unstubAllGlobals())

function renderAt(path: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: false,
      status: 503,
      statusText: 'down',
      json: async () => ({}),
      text: async () => '',
    })),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <Providers live={false} client={client}>
      <RouterProvider router={router} />
    </Providers>,
  )
}

describe('App shell', () => {
  it.each([
    ['/', 'Panel'],
    ['/coin/BTCUSDT', 'Coin detay'],
    ['/news', 'Haber akışı'],
    ['/predictions', 'Tahmin geçmişi'],
    ['/calibration', 'Kalibrasyon'],
    ['/settings', 'Ayarlar'],
    ['/costs', 'Maliyet'],
  ])('renders %s with heading %s', async (path, heading) => {
    renderAt(path)
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Ana menü' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Veri durumu' })).toBeInTheDocument()
  })
})
