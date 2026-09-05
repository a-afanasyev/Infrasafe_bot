import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

const root = resolve(__dirname, '../..')
export default defineConfig({
  testDir: './payment-control',
  testMatch: '*.spec.ts',
  outputDir: './artifacts/payment-control',
  workers: 1,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:5179', locale: 'ru-RU', screenshot: 'only-on-failure', viewport: { width: 1440, height: 1000 } },
  webServer: [
    { command: '.venv/bin/python tests/e2e/payment-control/server.py', cwd: root, url: 'http://127.0.0.1:18085/health', reuseExistingServer: false },
    { command: 'VITE_API_URL=http://127.0.0.1:18085 VITE_WS_URL=ws://127.0.0.1:18085 VITE_PAYMENTS_ENABLED=true npm --prefix frontend run dev -- --host 127.0.0.1 --port 5179', cwd: root, url: 'http://127.0.0.1:5179/uk/', reuseExistingServer: false },
  ],
})
