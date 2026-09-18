import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { ReactNode } from 'react'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../test/test-utils'
import { server } from '../test/msw/server'
import ResourceAccountingSection from './ResourceAccountingSection'

// TEST-068: host-обёртка раздела «Учёт ресурсов». Сам модуль (провайдер,
// роуты, сессия) замокан — проверяем логику обёртки: порядок configure →
// ensureSession, минтинг тикета через наш backend, single-flight на 401,
// состояния loading/error/ready, под-навигация по роли.

const mod = vi.hoisted(() => ({
  role: 'resource_admin' as string,
  ensureResourceSession: vi.fn(),
  configureResourceApi: vi.fn(),
}))

vi.mock('@/features/resource-accounting', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/resource-accounting')>()
  return {
    ...actual,
    ensureResourceSession: mod.ensureResourceSession,
    configureResourceApi: mod.configureResourceApi,
    useResourceAuth: () => ({ role: mod.role }),
    ResourceAccountingProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
    ResourceAccountingRoutes: () => <div>ROUTES</div>,
  }
})

let mints: number

beforeEach(() => {
  mints = 0
  mod.role = 'resource_admin'
  mod.configureResourceApi.mockReset()
  mod.ensureResourceSession.mockReset()
  // По умолчанию: сессии нет → mint → «обмен» (здесь — просто вызов mint).
  mod.ensureResourceSession.mockImplementation(async (mint: () => Promise<string>) => {
    const ticket = await mint()
    if (!ticket) throw new Error('no ticket')
  })
  server.use(
    http.post('*/api/v2/resource-accounting/ticket', () => {
      mints += 1
      return HttpResponse.json({ ticket: 'T-1' })
    }),
  )
})

describe('ResourceAccountingSection', () => {
  it('loading → ready: configure вызван до ensureSession, тикет заминчен нашим backend, рендерятся nav и роуты', async () => {
    render(<ResourceAccountingSection />, { routerEntries: ['/dashboard/resource-accounting/meters'] })
    expect(document.querySelector('.animate-spin, [role="status"]') ?? screen.queryByText('ROUTES')).not.toBeNull()
    expect(await screen.findByText('ROUTES')).toBeInTheDocument()

    expect(mod.configureResourceApi).toHaveBeenCalledTimes(1)
    expect(mod.configureResourceApi.mock.calls[0][0]).toMatchObject({ baseUrl: '/uk/api/resource' })
    expect(mod.configureResourceApi.mock.invocationCallOrder[0]).toBeLessThan(mod.ensureResourceSession.mock.invocationCallOrder[0])
    expect(mints).toBe(1)

    // Админ: все ссылки, включая «Журнал»; «Ввод показаний» — потому что может вносить.
    for (const label of ['Сводка', 'Ввод показаний', 'Счётчики', 'Объекты', 'Акты сверки', 'Поставщики', 'Журнал']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(screen.getByRole('link', { name: 'Счётчики' })).toHaveAttribute('href', '/dashboard/resource-accounting/meters')
    expect(screen.getByRole('link', { name: 'Счётчики' }).className).toContain('border-accent')
    expect(screen.getByRole('link', { name: 'Сводка' }).className).not.toContain('border-accent')
  })

  it('viewer: «Ведомость» вместо «Ввода показаний», без «Журнала»; meter_entry: навигации нет', async () => {
    mod.role = 'resource_viewer'
    const { unmount } = render(<ResourceAccountingSection />)
    await screen.findByText('ROUTES')
    expect(screen.getByRole('link', { name: 'Ведомость' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Ввод показаний' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Журнал' })).toBeNull()
    unmount()

    mod.role = 'resource_meter_entry'
    render(<ResourceAccountingSection />)
    await screen.findByText('ROUTES')
    expect(screen.queryByRole('navigation')).toBeNull()
  })

  it('сессию поднять не удалось → текст недоступности', async () => {
    mod.ensureResourceSession.mockRejectedValue(new Error('down'))
    render(<ResourceAccountingSection />)
    expect(await screen.findByText(/временно недоступен/)).toBeInTheDocument()
    expect(screen.queryByText('ROUTES')).toBeNull()
  })

  it('single-flight: параллельные onUnauthorized склеиваются в один ensureSession', async () => {
    render(<ResourceAccountingSection />)
    await screen.findByText('ROUTES')
    const callsBefore = mod.ensureResourceSession.mock.calls.length

    // Долгий ensureSession: пока он в полёте, повторные 401 не запускают новый.
    let release: () => void = () => {}
    mod.ensureResourceSession.mockImplementation(() => new Promise<void>((r) => { release = r }))
    const { onUnauthorized } = mod.configureResourceApi.mock.calls[0][0] as { onUnauthorized: () => void }
    onUnauthorized()
    onUnauthorized()
    onUnauthorized()
    expect(mod.ensureResourceSession.mock.calls.length).toBe(callsBefore + 1)

    release()
    await waitFor(() => Promise.resolve())
    await new Promise((r) => setTimeout(r, 0))
    // После завершения — новый 401 запускает свежий цикл.
    onUnauthorized()
    expect(mod.ensureResourceSession.mock.calls.length).toBe(callsBefore + 2)
  })
})
