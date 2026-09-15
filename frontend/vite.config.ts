import { execSync } from 'node:child_process'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Çalışan arayüzün commit'i: Docker'da build arg ile, geliştirmede git'ten okunur.
// Alt şeritte gösterilir; API'nin commit'iyle karşılaştırılır (eski sekme / eski sunucu tespiti).
function resolveGitSha(): string {
  if (process.env.VITE_GIT_SHA) return process.env.VITE_GIT_SHA
  try {
    return execSync('git rev-parse --short HEAD', { encoding: 'utf8' }).trim()
  } catch {
    return 'bilinmiyor'
  }
}

// Geliştirmede /api ve /ws istekleri backend'e (8000) proxy'lenir; tarayıcı tek origin görür.
const proxy = {
  '/api': { target: 'http://localhost:8000', changeOrigin: true },
  '/ws': { target: 'ws://localhost:8000', ws: true },
}

export default defineConfig({
  define: {
    __GIT_SHA__: JSON.stringify(resolveGitSha()),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // Tek adres: geliştirmede de, Docker'da da http://localhost:3000
  server: { port: 3000, strictPort: true, proxy },
  preview: { port: 3000, strictPort: true, proxy },
  build: { sourcemap: false },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
