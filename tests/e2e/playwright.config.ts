import { defineConfig, devices } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './specs',
  outputDir: './artifacts',
  timeout: 30_000,
  retries: 1,
  workers: 1, // serial — single dev server, no parallelism issues
  reporter: [
    ['list'],
    ['html', { outputFolder: './html-report', open: 'never' }],
  ],
  use: {
    baseURL: BASE_URL,
    headless: true,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'ru-RU',
    viewport: { width: 1280, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
