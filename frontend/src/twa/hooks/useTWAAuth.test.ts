import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { getTwaRefreshToken, setTwaRefreshToken, clearTwaRefreshToken } from '../twaToken'
import { twaClient } from '../twaClient'
import { useTWAAuth } from './useTWAAuth'

// A9-P3-22: ветки TWA-авторизации — initData-логин, refresh без initData,
// TWA-05 (нет повторного входа при уже полученном токене) и TWA-06/08
// (событие `twa:auth-failed` сбрасывает токен → повторный вход по initData).
// JSON-тела без formData — MSW здесь надёжен.

const sdk = vi.hoisted(() => ({ initData: '' }))
vi.mock('./useTelegramSDK', () => ({
  useTelegramSDK: () => ({ initData: sdk.initData }),
}))

const INIT_DATA = 'query_id=AA&user=%7B%22id%22%3A42%7D&hash=deadbeef'

type Calls = { twa: unknown[]; refresh: unknown[] }

function mockAuth(opts: {
  twa?: (n: number) => Response
  refresh?: (n: number) => Response
}): Calls {
  const calls: Calls = { twa: [], refresh: [] }
  server.use(
    http.post('*/api/v2/auth/twa', async ({ request }) => {
      calls.twa.push(await request.json())
      return opts.twa
        ? opts.twa(calls.twa.length)
        : HttpResponse.json({ detail: 'unexpected' }, { status: 500 })
    }),
    http.post('*/api/v2/auth/refresh', async ({ request }) => {
      calls.refresh.push(await request.json())
      return opts.refresh
        ? opts.refresh(calls.refresh.length)
        : HttpResponse.json({ detail: 'unexpected' }, { status: 500 })
    }),
  )
  return calls
}

const tokens = (n: number) =>
  HttpResponse.json({ access_token: `access-${n}`, refresh_token: `refresh-${n}` })

let errorSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  sdk.initData = ''
  clearTwaRefreshToken()
  errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  errorSpy.mockRestore()
  delete twaClient.defaults.headers.common['Authorization']
})

describe('useTWAAuth — initData login', () => {
  it('posts init_data to /auth/twa and stores both tokens', async () => {
    sdk.initData = INIT_DATA
    const calls = mockAuth({ twa: tokens })

    const { result } = renderHook(() => useTWAAuth())
    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.accessToken).toBe('access-1')
    expect(result.current.isAuthenticated).toBe(true)
    expect(calls.twa).toEqual([{ init_data: INIT_DATA }])
    expect(calls.refresh).toEqual([])
    expect(getTwaRefreshToken()).toBe('refresh-1')
  })

  it('failed /auth/twa leaves the user unauthenticated and logs only the message (FE-06)', async () => {
    sdk.initData = INIT_DATA
    mockAuth({ twa: () => HttpResponse.json({ detail: 'bad hash' }, { status: 401 }) })

    const { result } = renderHook(() => useTWAAuth())

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.accessToken).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
    expect(getTwaRefreshToken()).toBeNull()
    expect(errorSpy).toHaveBeenCalledTimes(1)
    const logged = errorSpy.mock.calls[0]
    expect(logged[0]).toBe('TWA auth failed:')
    expect(typeof logged[1]).toBe('string')
    // initData (подписанные данные пользователя) в консоль не утекают.
    expect(JSON.stringify(logged)).not.toContain('deadbeef')
  })

  it('does not overwrite an existing refresh token when /auth/twa fails', async () => {
    sdk.initData = INIT_DATA
    setTwaRefreshToken('old-refresh')
    const calls = mockAuth({ twa: () => HttpResponse.json({}, { status: 500 }) })

    const { result } = renderHook(() => useTWAAuth())

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isAuthenticated).toBe(false)
    // С initData refresh-ветка не используется вовсе.
    expect(calls.refresh).toEqual([])
    expect(getTwaRefreshToken()).toBe('old-refresh')
  })

  it('authenticates once initData arrives after the first render (TWA-05)', async () => {
    const calls = mockAuth({ twa: tokens })

    const { result, rerender } = renderHook(() => useTWAAuth())
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isAuthenticated).toBe(false)
    expect(calls.twa).toEqual([])

    sdk.initData = INIT_DATA
    rerender()

    await waitFor(() => expect(result.current.accessToken).toBe('access-1'))
    expect(calls.twa).toEqual([{ init_data: INIT_DATA }])
  })

  it('does not re-authenticate when initData changes after a token is held (TWA-05)', async () => {
    sdk.initData = INIT_DATA
    const calls = mockAuth({ twa: tokens })

    const { result, rerender } = renderHook(() => useTWAAuth())
    await waitFor(() => expect(result.current.accessToken).toBe('access-1'))

    sdk.initData = `${INIT_DATA}&late=1`
    rerender()
    // Дать эффектам шанс отработать — повторного POST быть не должно.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20))
    })

    expect(calls.twa).toHaveLength(1)
    expect(result.current.accessToken).toBe('access-1')
  })
})

describe('useTWAAuth — no initData', () => {
  it('without a refresh token makes no request and stops loading', async () => {
    const calls = mockAuth({})

    const { result } = renderHook(() => useTWAAuth())

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isAuthenticated).toBe(false)
    expect(calls).toEqual({ twa: [], refresh: [] })
    expect(errorSpy).not.toHaveBeenCalled()
  })

  it('refreshes with the in-memory refresh token and rotates it', async () => {
    setTwaRefreshToken('mem-refresh')
    const calls = mockAuth({ refresh: tokens })

    const { result } = renderHook(() => useTWAAuth())

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.accessToken).toBe('access-1')
    expect(calls.refresh).toEqual([{ refresh_token: 'mem-refresh' }])
    expect(calls.twa).toEqual([])
    expect(getTwaRefreshToken()).toBe('refresh-1')
  })

  it('clears the refresh token when refresh fails and does not fall back to /auth/twa', async () => {
    setTwaRefreshToken('stale-refresh')
    const calls = mockAuth({ refresh: () => HttpResponse.json({}, { status: 401 }) })

    const { result } = renderHook(() => useTWAAuth())

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isAuthenticated).toBe(false)
    expect(calls.refresh).toHaveLength(1)
    expect(calls.twa).toEqual([])
    expect(getTwaRefreshToken()).toBeNull()
    // Сбой refresh гасится внутренним catch — не логируется как общий сбой входа.
    expect(errorSpy).not.toHaveBeenCalled()
  })
})

describe('useTWAAuth — twa:auth-failed', () => {
  it('drops the token and re-authenticates via fresh initData (TWA-06/08)', async () => {
    sdk.initData = INIT_DATA
    const calls = mockAuth({ twa: tokens })

    const { result } = renderHook(() => useTWAAuth())
    await waitFor(() => expect(result.current.accessToken).toBe('access-1'))

    act(() => {
      window.dispatchEvent(new CustomEvent('twa:auth-failed'))
    })

    await waitFor(() => expect(result.current.accessToken).toBe('access-2'))
    expect(calls.twa).toHaveLength(2)
    expect(getTwaRefreshToken()).toBe('refresh-2')
  })

  it('ends unauthenticated when there is neither initData nor a refresh token', async () => {
    setTwaRefreshToken('mem-refresh')
    const calls = mockAuth({ refresh: tokens })

    const { result } = renderHook(() => useTWAAuth())
    await waitFor(() => expect(result.current.accessToken).toBe('access-1'))

    // Интерцептор twaClient перед событием уже очистил refresh-токен.
    clearTwaRefreshToken()
    act(() => {
      window.dispatchEvent(new CustomEvent('twa:auth-failed'))
    })

    await waitFor(() => expect(result.current.accessToken).toBeNull())
    expect(result.current.isAuthenticated).toBe(false)
    expect(calls.refresh).toHaveLength(1)
    expect(calls.twa).toEqual([])
  })

  it('removes the listener on unmount', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    mockAuth({})

    const { result, unmount } = renderHook(() => useTWAAuth())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const handler = addSpy.mock.calls.find(([type]) => type === 'twa:auth-failed')?.[1]
    expect(handler).toBeTypeOf('function')
    unmount()
    expect(removeSpy).toHaveBeenCalledWith('twa:auth-failed', handler)

    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it('end-to-end: twaClient 401 + failed refresh dispatches the event and the hook re-inits', async () => {
    sdk.initData = INIT_DATA
    const calls = mockAuth({
      twa: tokens,
      refresh: () => HttpResponse.json({}, { status: 401 }),
    })
    server.use(
      http.get('*/api/v2/twa/probe', () => HttpResponse.json({}, { status: 401 })),
    )

    const { result } = renderHook(() => useTWAAuth())
    await waitFor(() => expect(result.current.accessToken).toBe('access-1'))
    expect(getTwaRefreshToken()).toBe('refresh-1')

    const onFailed = vi.fn()
    window.addEventListener('twa:auth-failed', onFailed)
    try {
      await act(async () => {
        await expect(twaClient.get('/api/v2/twa/probe')).rejects.toMatchObject({
          response: { status: 401 },
        })
      })
    } finally {
      window.removeEventListener('twa:auth-failed', onFailed)
    }

    expect(onFailed).toHaveBeenCalledTimes(1)
    expect(calls.refresh).toEqual([{ refresh_token: 'refresh-1' }])
    await waitFor(() => expect(result.current.accessToken).toBe('access-2'))
    expect(calls.twa).toHaveLength(2)
  })
})
