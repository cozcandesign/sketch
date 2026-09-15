import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Geliştirmede /api ve /ws istekleri backend'e (8000) proxy'lenir; tarayıcı tek origin görür.
const proxy = {
  '/api': { target: 'http://localhost:8000', changeOrigin: true },
  '/ws': { target: 'ws://localhost:8000', ws: true },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 3000, strictPort: true, proxy },
  build: { sourcemap: false },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
