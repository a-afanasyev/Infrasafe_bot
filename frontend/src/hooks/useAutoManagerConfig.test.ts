import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { waitFor } from '@testing-library/react'
import { renderHook } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { apiClient } from '../api/client'
import { publicClient } from '../api/publicClient'

// Capture the raw options object handed to react-query's useQuery so we can
// assert on refetchInterval/refetchOnWindowFocus directly — these are the
// plan-mandated deviation from the useBoardConfig clone (bot<->dashboard
// sync within <=30s) and must be locked in by a test, not just present by
// accident. vi.spyOn can't target ESM namespace exports directly (Vitest
// throws "Module namespace is not configurable"), so we wrap the real
// implementation via vi.mock + importOriginal instead.
const useQuerySpy = vi.fn()
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: (options: unknown) => {
      useQuerySpy(options)
      return actual.useQuery(options as never)
    },
  }
})

const CONFIG = {
  enabled: true,
  mode: 'rule' as const,
  window_start: '20:00',
  window_end: '08:00',
  timezone: 'Asia/Tashkent',
  max_requests_per_run: 10,
}

describe('useAutoManagerConfig', () => {
  it('GETs /api/v2/auto-manager-config via apiClient (not publicClient)', async () => {
    const apiSpy = vi.spyOn(apiClient, 'get')
    const publicSpy = vi.spyOn(publicClient, 'get')
    server.use(
      http.get('*/api/v2/auto-manager-config', () => HttpResponse.json(CONFIG)),
    )
    const { useAutoManagerConfig } = await import('./useAutoManagerConfig')
    const { result } = renderHook(() => useAutoManagerConfig())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(CONFIG)
    expect(apiSpy).toHaveBeenCalledWith('/api/v2/auto-manager-config')
    expect(publicSpy).not.toHaveBeenCalled()
    apiSpy.mockRestore()
    publicSpy.mockRestore()
  })

  it('configures queryKey + refetchInterval: 30_000 + refetchOnWindowFocus: true', async () => {
    server.use(
      http.get('*/api/v2/auto-manager-config', () => HttpResponse.json(CONFIG)),
    )
    const { useAutoManagerConfig } = await import('./useAutoManagerConfig')
    renderHook(() => useAutoManagerConfig())
    expect(useQuerySpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ['auto-manager-config'],
        refetchInterval: 30_000,
        refetchOnWindowFocus: true,
      }),
    )
    // Explicitly NOT the board_config clone's staleTime: 60_000 — polling
    // replaces it as the freshness mechanism for this endpoint.
    const lastCallOptions = useQuerySpy.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(lastCallOptions.staleTime).toBeUndefined()
  })
})

describe('useUpdateAutoManagerConfig', () => {
  it('re-fetches the LATEST server state before PUTting, merges the patch over that (not stale cache)', async () => {
    // Regression: the mutation must build its PUT body from a fresh GET, not
    // from whatever the caller happened to have cached — otherwise a caller
    // holding stale data (e.g. the dashboard's 30s-old poll) could silently
    // revert a more recent change made by the bot in between.
    const SERVER_LATEST = { ...CONFIG, enabled: true, window_start: '21:00' }
    let getCallCount = 0
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get('*/api/v2/auto-manager-config', () => {
        getCallCount += 1
        return HttpResponse.json(SERVER_LATEST)
      }),
      http.put('*/api/v2/auto-manager-config', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(putBody)
      }),
    )
    const successSpy = vi.spyOn(toast, 'success')
    const { useUpdateAutoManagerConfig } = await import('./useAutoManagerConfig')
    const { result } = renderHook(() => useUpdateAutoManagerConfig())

    // Caller only sends a PATCH (window_end) — deliberately NOT enabled, to
    // prove the merge pulls `enabled` from the fresh GET, not from thin air.
    result.current.mutate({ window_end: '09:00' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(getCallCount).toBeGreaterThanOrEqual(1)
    expect(putBody).toEqual({ ...SERVER_LATEST, window_end: '09:00' })
    expect(successSpy).toHaveBeenCalled()
    successSpy.mockRestore()
  })

  it('a stale-cache scenario does not revert a field the patch never touched', async () => {
    // Concretely: bot flips enabled=true server-side; dashboard (holding an
    // old enabled=false in its own component state) saves only the window.
    // The PUT must still carry enabled=true (from the fresh fetch), not the
    // dashboard's stale false.
    const SERVER_STATE_AFTER_BOT_CHANGE = { ...CONFIG, enabled: true }
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get('*/api/v2/auto-manager-config', () => HttpResponse.json(SERVER_STATE_AFTER_BOT_CHANGE)),
      http.put('*/api/v2/auto-manager-config', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(putBody)
      }),
    )
    const { useUpdateAutoManagerConfig } = await import('./useAutoManagerConfig')
    const { result } = renderHook(() => useUpdateAutoManagerConfig())

    result.current.mutate({ window_start: '22:00' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect((putBody as unknown as typeof CONFIG).enabled).toBe(true)
  })

  it('reports an error toast on a 422 without crashing', async () => {
    server.use(
      http.get('*/api/v2/auto-manager-config', () => HttpResponse.json(CONFIG)),
      http.put('*/api/v2/auto-manager-config', () =>
        HttpResponse.json({ detail: 'window_start: invalid format' }, { status: 422 }),
      ),
    )
    const errorSpy = vi.spyOn(toast, 'error')
    const { useUpdateAutoManagerConfig } = await import('./useAutoManagerConfig')
    const { result } = renderHook(() => useUpdateAutoManagerConfig())
    result.current.mutate({ window_start: 'bad' })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(errorSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ description: 'window_start: invalid format' }),
    )
    errorSpy.mockRestore()
  })
})
