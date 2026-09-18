import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../test/msw/server'
import { useAuthStore } from './authStore'

// Cold-start cookie probe (bootstrap): a fresh tab has no per-tab auth flag in
// sessionStorage but may carry a valid shared httpOnly cookie. bootstrap probes
// /profile (with a manual refresh fallback) to recover the session.

beforeEach(() => {
  sessionStorage.clear()
  useAuthStore.setState({ user: null, isAuthenticated: false, hydrating: true })
})

describe('authStore.bootstrap — shared-cookie session recovery', () => {
  it('fast-path: already authenticated → resolves hydrating without a network call', async () => {
    // No handlers registered: onUnhandledRequest:"error" would fail the test if
    // bootstrap probed the network here.
    useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: true })
    await useAuthStore.getState().bootstrap()
    const s = useAuthStore.getState()
    expect(s.isAuthenticated).toBe(true)
    expect(s.hydrating).toBe(false)
  })

  it('valid cookie: /profile 200 → authenticated', async () => {
    server.use(
      http.get('*/api/v2/profile', () => HttpResponse.json({ id: 7, roles: ['manager'], first_name: 'M' })),
    )
    await useAuthStore.getState().bootstrap()
    const s = useAuthStore.getState()
    expect(s.isAuthenticated).toBe(true)
    expect(s.user).toEqual({ id: 7, roles: ['manager'], first_name: 'M' })
    expect(s.hydrating).toBe(false)
  })

  it('expired access cookie: /profile 401 → refresh 200 → re-probe 200 → authenticated', async () => {
    let profileCalls = 0
    server.use(
      http.get('*/api/v2/profile', () => {
        profileCalls += 1
        if (profileCalls === 1) return new HttpResponse(null, { status: 401 })
        return HttpResponse.json({ id: 9, roles: ['admin'] })
      }),
      http.post('*/api/v2/auth/refresh', () => HttpResponse.json({ ok: true })),
    )
    await useAuthStore.getState().bootstrap()
    const s = useAuthStore.getState()
    expect(profileCalls).toBe(2)
    expect(s.isAuthenticated).toBe(true)
    expect(s.user).toEqual({ id: 9, roles: ['admin'] })
    expect(s.hydrating).toBe(false)
  })

  it('no session: /profile 401 + refresh 401 → not authenticated, hydrating resolved', async () => {
    server.use(
      http.get('*/api/v2/profile', () => new HttpResponse(null, { status: 401 })),
      http.post('*/api/v2/auth/refresh', () => new HttpResponse(null, { status: 401 })),
    )
    await useAuthStore.getState().bootstrap()
    const s = useAuthStore.getState()
    expect(s.isAuthenticated).toBe(false)
    expect(s.user).toBeNull()
    expect(s.hydrating).toBe(false)
  })
})

// AUD7-CODE-01: bootstrap ходил в /refresh напрямую (publicClient.post) мимо
// refresh-координатора client.ts. Две холодные вкладки (или StrictMode-двойной
// bootstrap) отправляли один и тот же refresh-cookie дважды; после атомарной
// ротации второй запрос — reuse → сервер отзывает всю family, сессия падает.
describe('authStore.bootstrap — через refresh-координатор', () => {
  let refreshPosts = 0
  let profileGets = 0

  beforeEach(() => {
    refreshPosts = 0
    profileGets = 0
    localStorage.clear()
    server.use(
      // Первый probe — 401 (просроченный access), после refresh — 200.
      http.get('*/api/v2/profile', () => {
        profileGets += 1
        return refreshPosts === 0
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json({ id: 7, roles: ['manager'], first_name: 'M' })
      }),
      http.post('*/api/v2/auth/refresh', () => {
        refreshPosts += 1
        return HttpResponse.json({ ok: true })
      }),
    )
    // Сериализующий Web Locks-стаб, как в client.crossTab.test.ts.
    let tail: Promise<unknown> = Promise.resolve()
    Object.defineProperty(navigator, 'locks', {
      configurable: true,
      value: {
        request: (_name: string, cb: () => Promise<void>) => {
          const run = tail.then(() => cb())
          tail = run.catch(() => undefined)
          return run
        },
      },
    })
  })

  afterEach(() => {
    Reflect.deleteProperty(navigator as unknown as Record<string, unknown>, 'locks')
    vi.resetModules()
  })

  it('два параллельных bootstrap в одной вкладке (StrictMode) — один POST /refresh', async () => {
    await Promise.all([useAuthStore.getState().bootstrap(), useAuthStore.getState().bootstrap()])

    expect(refreshPosts).toBe(1)
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(profileGets).toBe(2) // probe (401) + re-probe (200), без дублей
  })

  it('две холодные вкладки — один POST /refresh, обе получают сессию', async () => {
    vi.resetModules()
    const tabA = await import('./authStore')
    vi.resetModules()
    const tabB = await import('./authStore')
    tabA.useAuthStore.setState({ user: null, isAuthenticated: false, hydrating: true })
    tabB.useAuthStore.setState({ user: null, isAuthenticated: false, hydrating: true })

    await Promise.all([tabA.useAuthStore.getState().bootstrap(), tabB.useAuthStore.getState().bootstrap()])

    expect(refreshPosts).toBe(1)
    expect(tabA.useAuthStore.getState().isAuthenticated).toBe(true)
    expect(tabB.useAuthStore.getState().isAuthenticated).toBe(true)
  })

  it('нет сессии: refresh 401 → тихий отказ без редиректа на /login', async () => {
    server.use(http.post('*/api/v2/auth/refresh', () => new HttpResponse(null, { status: 401 })))
    const before = window.location.href

    await useAuthStore.getState().bootstrap()

    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(useAuthStore.getState().hydrating).toBe(false)
    expect(window.location.href).toBe(before)
  })
})
