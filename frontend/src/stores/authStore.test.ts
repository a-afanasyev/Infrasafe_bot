import { describe, it, expect, beforeEach } from 'vitest'
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
