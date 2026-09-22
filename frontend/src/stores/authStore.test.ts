import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../test/msw/server'
import { useAuthStore } from './authStore'
import { queryClient } from '../api/queryClient'

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

// A9-P2-29: следующий пользователь в той же вкладке не должен видеть кэш
// предыдущего (канбан, ПДн жителей, media-blob) — logout/login чистят QueryClient.
describe('authStore — изоляция кэша QueryClient между пользователями', () => {
  it('logout чистит все запросы (включая media-blob)', async () => {
    server.use(http.post('*/api/v2/auth/logout', () => HttpResponse.json({ ok: true })))
    queryClient.setQueryData(['kanban', 'all'], [{ id: 1 }])
    queryClient.setQueryData(['media-blob', 5], 'data:image/png;base64,AAAA')
    useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: false })

    await useAuthStore.getState().logout()

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })

  it('logout чистит кэш и при ошибке серверного вызова', async () => {
    server.use(http.post('*/api/v2/auth/logout', () => new HttpResponse(null, { status: 500 })))
    queryClient.setQueryData(['residents'], [{ id: 2 }])
    await useAuthStore.getState().logout()
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
  })

  it('logout отменяет in-flight запрос: ответ старой сессии не попадает в кэш', async () => {
    server.use(http.post('*/api/v2/auth/logout', () => HttpResponse.json({ ok: true })))
    let resolveFetch: (v: string[]) => void = () => {}
    const pending = queryClient.fetchQuery({
      queryKey: ['residents', 'pii'],
      queryFn: () => new Promise<string[]>((r) => { resolveFetch = r }),
    }).catch(() => undefined)
    await useAuthStore.getState().logout()
    resolveFetch(['Иванов'])
    await pending
    expect(queryClient.getQueryData(['residents', 'pii'])).toBeUndefined()
  })

  it('login сбрасывает остатки прошлой сессии', async () => {
    server.use(http.get('*/api/v2/profile', () => HttpResponse.json({ id: 3, roles: ['manager'] })))
    queryClient.setQueryData(['kanban', 'all'], [{ id: 1 }])
    await useAuthStore.getState().login()
    expect(queryClient.getQueryData(['kanban', 'all'])).toBeUndefined()
    expect(useAuthStore.getState().user).toEqual({ id: 3, roles: ['manager'] })
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
