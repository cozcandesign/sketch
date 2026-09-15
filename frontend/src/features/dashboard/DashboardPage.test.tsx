import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { Providers } from '@/app/providers'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { health, marketState, mockApi } from '@/test/mockApi'

afterEach(() => vi.unstubAllGlobals())

function renderPage() {
  mockApi({
    '/symbols': { symbols: ['BTCUSDT'], timezone: 'Europe/Istanbul' },
    '/market/BTCUSDT': marketState,
    '/health': health,
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <Providers live={false} client={client}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </Providers>,
  )
}

describe('DashboardPage', () => {
  it('shows the coin card with price, change and horizon probability', async () => {
    renderPage()
    expect(await screen.findByText('BTCUSDT')).toBeInTheDocument()
    expect(await screen.findByText('%62')).toBeInTheDocument()
    expect(screen.getByText(/24s/)).toBeInTheDocument()
    expect(screen.getByText('30 dk')).toBeInTheDocument()
  })

  it('says that only reference predictors are running', async () => {
    renderPage()
    expect(await screen.findByText(/referans tahminciler/i)).toBeInTheDocument()
  })
})
