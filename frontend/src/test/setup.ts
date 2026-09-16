import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

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
