import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// vitest globals kapalı: Testing Library otomatik temizlik yapmaz, her testten sonra DOM temizlenir.
afterEach(() => cleanup())
