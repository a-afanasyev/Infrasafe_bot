import { describe, it, expect, vi, beforeAll, afterEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { render } from '../test/test-utils'
import ResourceAccountingPage from './ResourceAccountingPage'

const RES_URL = 'https://resources.infrasafe.uz'
const RES_ORIGIN = 'https://resources.infrasafe.uz'

// crypto.randomUUID есть в браузерах и Node ≥18; подстрахуемся для jsdom.
beforeAll(() => {
  const c = globalThis.crypto
  if (!c || typeof c.randomUUID !== 'function') {
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: { ...(c ?? {}), randomUUID: () => 'nonce-' + Math.random().toString(16).slice(2) },
    })
  }
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

function fireReady(source: { postMessage: ReturnType<typeof vi.fn> }, origin = RES_ORIGIN) {
  const ev = new MessageEvent('message', { data: { type: 'resource-accounting:ready' }, origin })
  // jsdom не даёт задать source через init — вешаем напрямую на инстанс.
  Object.defineProperty(ev, 'source', { value: source })
  window.dispatchEvent(ev)
}

describe('ResourceAccountingPage', () => {
  it('shows a placeholder and no iframe when VITE_RESOURCES_URL is empty', () => {
    vi.stubEnv('VITE_RESOURCES_URL', '')
    const { container } = render(<ResourceAccountingPage />)
    expect(screen.getByText('Раздел не настроен для этого инстанса.')).toBeInTheDocument()
    expect(container.querySelector('iframe')).toBeNull()
  })

  it('renders the iframe pointing at VITE_RESOURCES_URL', () => {
    vi.stubEnv('VITE_RESOURCES_URL', RES_URL)
    const { container } = render(<ResourceAccountingPage />)
    const iframe = container.querySelector('iframe')
    expect(iframe).not.toBeNull()
    expect(iframe?.getAttribute('src')).toBe(RES_URL)
  })

  it('issues a ticket and posts it back to the message source on ready', async () => {
    vi.stubEnv('VITE_RESOURCES_URL', RES_URL)
    render(<ResourceAccountingPage />)

    const source = { postMessage: vi.fn() }
    fireReady(source)

    await waitFor(() => expect(source.postMessage).toHaveBeenCalledTimes(1))
    const [msg, targetOrigin] = source.postMessage.mock.calls[0]
    expect(msg.type).toBe('resource-accounting:ticket')
    expect(msg.ticket).toBe('opaque-test-ticket')
    expect(typeof msg.nonce).toBe('string')
    // targetOrigin строго = origin ресурсов, не '*'.
    expect(targetOrigin).toBe(RES_ORIGIN)
  })

  it('ignores messages from an unexpected origin (no ticket issued)', async () => {
    vi.stubEnv('VITE_RESOURCES_URL', RES_URL)
    render(<ResourceAccountingPage />)

    const source = { postMessage: vi.fn() }
    fireReady(source, 'https://evil.example')

    // дать возможному async-обработчику отработать
    await new Promise((r) => setTimeout(r, 30))
    expect(source.postMessage).not.toHaveBeenCalled()
  })

  it('opens the service in a new tab via window.open (opener preserved)', () => {
    vi.stubEnv('VITE_RESOURCES_URL', RES_URL)
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    render(<ResourceAccountingPage />)

    fireEvent.click(screen.getByText('Открыть в отдельной вкладке'))
    expect(openSpy).toHaveBeenCalledWith(RES_URL, '_blank')
  })

  it('resizes the iframe on a height message', async () => {
    vi.stubEnv('VITE_RESOURCES_URL', RES_URL)
    const { container } = render(<ResourceAccountingPage />)

    const ev = new MessageEvent('message', {
      data: { type: 'resource-accounting:height', height: 1234 },
      origin: RES_ORIGIN,
    })
    window.dispatchEvent(ev)

    await waitFor(() => {
      expect(container.querySelector('iframe')?.style.height).toBe('1234px')
    })
  })
})
