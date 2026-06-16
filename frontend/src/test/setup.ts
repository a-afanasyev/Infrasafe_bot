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

// jsdom lacks the pointer-capture / scroll APIs Radix UI relies on to open
// menus (DropdownMenu, Select). Stub them so userEvent can drive dropdowns.
Element.prototype.scrollIntoView = vi.fn()
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = vi.fn(() => false)
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = vi.fn()
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = vi.fn()
}

// @twa-dev/sdk удалён из зависимостей (DEAD-12, PR-4): 0 импортов в src —
// TWA-код работает напрямую через window.Telegram.WebApp.
