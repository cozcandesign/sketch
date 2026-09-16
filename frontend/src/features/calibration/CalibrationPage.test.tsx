import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { Providers } from '@/app/providers'
import { CalibrationPage } from '@/features/calibration/CalibrationPage'
import { calibration, mockApi } from '@/test/mockApi'

afterEach(() => vi.unstubAllGlobals())

function renderPage(data = calibration) {
  mockApi({ '/calibration': data })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <Providers live={false} client={client}>
      <CalibrationPage />
    </Providers>,
  )
}

describe('CalibrationPage', () => {
  it('shows headline metrics and the per-model table', async () => {
    renderPage()
    // Brier hem üst kartta hem ufuk tablosunda görünür
    expect(await screen.findAllByText('0,180')).toHaveLength(2)
    expect(screen.getAllByText('%75').length).toBeGreaterThan(0)
    expect(screen.getByText('Referans: taban oranı')).toBeInTheDocument()
    expect(screen.getByText('Kalibrasyon eğrisi')).toBeInTheDocument()
    expect(screen.getByText('Brier zaman serisi')).toBeInTheDocument()
  })

  it('explains the metrics in plain language', async () => {
    renderPage()
    expect(await screen.findByText(/Brier skoru 0.25 ise hiçbir bilgi yok/)).toBeInTheDocument()
  })

  it('shows the module table with the reference line and the verdict', async () => {
    renderPage()
    expect(await screen.findByText('Modül bazlı isabet')).toBeInTheDocument()
    expect(screen.getByText('teknik')).toBeInTheDocument()
    expect(screen.getByText('referansı geçiyor')).toBeInTheDocument()
    // Referans çizgisi (%51) yazılı olmalı: modülün aşması gereken eşik gizlenmez.
    expect(screen.getByText('%51')).toBeInTheDocument()
  })

  it('says a module is still being measured before 200 resolved predictions', async () => {
    renderPage({
      ...calibration,
      by_module: [
        { ...calibration.by_module[0]!, n: 40, has_proof_sample: false, beats_reference: true },
      ],
    })
    expect(await screen.findByText('ölçülüyor')).toBeInTheDocument()
  })

  it('shows an empty state before any prediction resolves', async () => {
    renderPage({ ...calibration, overall: { ...calibration.overall, n: 0 }, daily: [] })
    expect(await screen.findByText(/Henüz sonuçlanmış tahmin yok/)).toBeInTheDocument()
  })
})
