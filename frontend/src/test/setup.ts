import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { server } from './msw/server'

// MSW lifecycle — fail loudly on any request without a handler so missing
// fixtures surface immediately instead of hanging.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// jsdom lacks matchMedia (used by useMediaQuery / useTheme).
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
})

// @twa-dev/sdk удалён из зависимостей (DEAD-12, PR-4): 0 импортов в src —
// TWA-код работает напрямую через window.Telegram.WebApp.
