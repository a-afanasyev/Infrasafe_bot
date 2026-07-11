import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'

import { server } from '../test/msw/server'

// F-02: cross-tab refresh coordination. Two tabs (two module instances sharing
// the same origin's localStorage + a serializing Web Locks mock) must produce
// exactly ONE network /refresh — the tab that acquires the lock second sees the
// fresh `uk_refreshed_at` marker and skips its own POST (not just the parallel
// case: the second tab must not fire a redundant *sequential* refresh either).

interface LockManagerMock {
  request: (name: string, cb: () => Promise<void>) => Promise<void>
}

describe('refreshSession cross-tab coordination', () => {
  let postCount = 0
  let clock = 1000

  beforeEach(() => {
    postCount = 0
    clock = 1000
    vi.spyOn(Date, 'now').mockImplementation(() => ++clock)
    localStorage.clear()

    server.use(
      http.post('*/api/v2/auth/refresh', () => {
        postCount += 1
        return HttpResponse.json({ access_token: 'a', token_type: 'bearer' })
      }),
    )

    // Serializing Web Locks stub: callbacks run one at a time, in request order.
    let tail: Promise<unknown> = Promise.resolve()
    const locks: LockManagerMock = {
      request: (_name, cb) => {
        const run = tail.then(() => cb())
        tail = run.catch(() => undefined)
        return run
      },
    }
    Object.defineProperty(navigator, 'locks', { value: locks, configurable: true })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    Reflect.deleteProperty(navigator as unknown as Record<string, unknown>, 'locks')
    vi.resetModules()
  })

  it('two tabs issue exactly one network refresh; the second skips via the marker', async () => {
    vi.resetModules()
    const tabA = await import('./client')
    vi.resetModules()
    const tabB = await import('./client')

    await Promise.all([tabA.refreshSession(), tabB.refreshSession()])

    expect(postCount).toBe(1)
  })

  it('concurrent 401s within one tab dedup to a single refresh', async () => {
    vi.resetModules()
    const { refreshSession } = await import('./client')

    await Promise.all([refreshSession(), refreshSession(), refreshSession()])

    expect(postCount).toBe(1)
  })

  it('without Web Locks, localStorage-lock fallback still yields one refresh', async () => {
    // Simulate a browser lacking the Web Locks API.
    Reflect.deleteProperty(navigator as unknown as Record<string, unknown>, 'locks')
    // Real timers so the localStorage-lock sleeps advance.
    vi.spyOn(Date, 'now').mockRestore()

    vi.resetModules()
    const tabA = await import('./client')
    vi.resetModules()
    const tabB = await import('./client')

    await Promise.all([tabA.refreshSession(), tabB.refreshSession()])

    expect(postCount).toBe(1)
  })
})
