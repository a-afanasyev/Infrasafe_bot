import { describe, it, expect, vi } from 'vitest'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { http, HttpResponse } from 'msw'
import { waitFor, renderHook as rawRenderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider } from 'react-i18next'
import { toast } from 'sonner'
import { renderHook, testI18n } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { useElevatorsConfig, useSaveElevatorsConfig } from './useElevatorsConfig'
import type { ElevatorsConfigOut } from '../types/elevators'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

const CONFIG: ElevatorsConfigOut = {
  module_public: false,
  downtime_threshold_days: { not_working: 2, under_repair: null },
  resident_notifications: { repair_started: true, maintenance_started: false, back_in_service: true },
  staff_reminders: { maintenance: [30, 7, 1], certification: [60, 30], contract: [90], overdue_weekly: true },
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
}
function wrapperFor(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(I18nextProvider, { i18n: testI18n }, children),
    )
}

describe('useElevatorsConfig', () => {
  it('читает конфиг', async () => {
    server.use(http.get('*/api/v2/elevators/config', () => HttpResponse.json(CONFIG)))
    const { result } = renderHook(() => useElevatorsConfig())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.downtime_threshold_days.under_repair).toBeNull()
  })
})

describe('useSaveElevatorsConfig', () => {
  it('успех: ответ PUT кладётся в кеш конфига, инвалидируется сводка, тост', async () => {
    let body: Record<string, unknown> | null = null
    const saved = { ...CONFIG, downtime_threshold_days: { not_working: 5, under_repair: null } }
    server.use(
      http.put('*/api/v2/elevators/config', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(saved)
      }),
    )
    const qc = makeClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const setData = vi.spyOn(qc, 'setQueryData')
    const { result } = rawRenderHook(() => useSaveElevatorsConfig(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ downtime_threshold_days: { not_working: 5, under_repair: null } })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toEqual({ downtime_threshold_days: { not_working: 5, under_repair: null } })
    // ответ PUT — новый кеш конфига (без лишнего GET); gcTime=0 в тесте сразу
    // чистит запись без наблюдателя, поэтому проверяем вызов, а не getQueryData
    expect(setData).toHaveBeenCalledWith(['elevators-config'], saved)
    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey)
    expect(keys).toContainEqual(['elevators-summary'])
    expect(toast.success).toHaveBeenCalledWith(testI18n.t('elevators.toast.configSaved'))
  })

  it('ошибка: toast.error с detail', async () => {
    server.use(
      http.put('*/api/v2/elevators/config', () =>
        HttpResponse.json({ detail: 'стадии должны убывать' }, { status: 422 }),
      ),
    )
    const { result } = renderHook(() => useSaveElevatorsConfig())
    result.current.mutate({ staff_reminders: { maintenance: [1, 7] } })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('стадии должны убывать')
  })
})
