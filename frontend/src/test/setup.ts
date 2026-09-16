import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// vitest globals kapalı: Testing Library otomatik temizlik yapmaz, her testten sonra DOM temizlenir.
afterEach(() => cleanup())

// jsdom'da ResizeObserver yok; mum grafiği genişliği buradan okur. Testte ölçüm gerekmez,
// bu yüzden hiçbir şey yapmayan bir yerine geçen yeterli.
if (!('ResizeObserver' in globalThis)) {
  class NoopResizeObserver implements ResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver = NoopResizeObserver
}

/**
 * jsdom'da canvas yoktur; `lightweight-charts` 2D bağlam bulamayınca çöker. Testlerde kütüphane
 * taklit edilir: sayfanın grafik ÇEVRESİNDEKİ davranışı (veri yükleme, boş durum, seçiciler)
 * ölçülür.
 *
 * Grafiğin kendisi — mumlar, EMA, seviye çizgileri, tahmin işaretçileri — gerçek tarayıcıda
 * doğrulanır. jsdom'da çizilemediği için burada "çalışıyor" demek yanıltıcı olurdu.
 */
vi.mock('lightweight-charts', () => {
  const series = {
    setData: vi.fn(),
    createPriceLine: vi.fn(() => ({})),
    removePriceLine: vi.fn(),
    applyOptions: vi.fn(),
  }
  return {
    CandlestickSeries: 'Candlestick',
    LineSeries: 'Line',
    createChart: vi.fn(() => ({
      addSeries: vi.fn(() => series),
      applyOptions: vi.fn(),
      timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
      remove: vi.fn(),
    })),
    createSeriesMarkers: vi.fn(() => ({ setMarkers: vi.fn() })),
  }
})
