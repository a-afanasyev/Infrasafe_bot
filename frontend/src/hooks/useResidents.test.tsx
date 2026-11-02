import { describe, it, expect, beforeEach, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import {
  useApproveResident,
  useAttachApartment,
  useBlockResident,
  useRejectBinding,
  useRemoveBinding,
  useUnblockResident,
  useUpdateBinding,
} from './useResidents'
import { toast } from 'sonner'
import i18n from '../i18n'

// Компонентные тесты мокают весь этот модуль, поэтому сам слой мутаций —
// тела запросов и набор инвалидируемых кэшей — оставался непроверенным. Ровно
// там и пряталась ошибка: инвалидировались кэши раздела «Жители», но не
// адресные, где ТЕ ЖЕ данные видны с другой стороны (список жильцов в карточке
// квартиры и их количество в таблицах). Здесь мокается только транспорт.

const api = vi.hoisted(() => ({
  post: vi.fn(() => Promise.resolve({ data: {} })),
  patch: vi.fn(() => Promise.resolve({ data: {} })),
  delete: vi.fn(() => Promise.resolve({ data: {} })),
}))

vi.mock('../api/client', () => ({ apiClient: api }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

/** Кэши, которые обязана сбросить ЛЮБАЯ мутация раздела. */
const EXPECTED_KEYS = [
  'residents', 'resident', 'residents-stats',
  'moderation', 'address-stats',
  'apartment-detail', 'apartments', 'all-apartments',
]

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const invalidated: unknown[][] = []
  const original = queryClient.invalidateQueries.bind(queryClient)
  queryClient.invalidateQueries = (filters?: { queryKey?: unknown[] }) => {
    if (filters?.queryKey) invalidated.push(filters.queryKey)
    return original(filters as never)
  }
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { wrapper, invalidated }
}

beforeEach(() => {
  api.post.mockClear()
  api.patch.mockClear()
  api.delete.mockClear()
})

describe('useResidents — мутации', () => {
  it('одобрение шлёт комментарий на правильный путь', async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useApproveResident(7), { wrapper })

    result.current.mutate({ comment: 'ок' })

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/api/v2/residents/7/approve', { comment: 'ок' })
  })

  it('блокировка шлёт причину', async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useBlockResident(7), { wrapper })

    result.current.mutate({ reason: 'мошенничество' })

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/api/v2/residents/7/block',
                                          { reason: 'мошенничество' })
  })

  it('привязка шлёт квартиру и оба флага', async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useAttachApartment(7), { wrapper })

    result.current.mutate({ apartment_id: 42, is_owner: true, is_primary: false })

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/api/v2/residents/7/apartments',
                                          { apartment_id: 42, is_owner: true, is_primary: false })
  })

  it('частичное обновление привязки НЕ шлёт неуказанные поля', async () => {
    // На бэкенде отсутствие поля = «не менять», а null = «сбросить». Прислать
    // is_primary: undefined в JSON нельзя — ключ обязан просто исчезнуть.
    const { wrapper } = setup()
    const { result } = renderHook(() => useUpdateBinding(7), { wrapper })

    result.current.mutate({ uaId: 11, is_owner: true })

    await waitFor(() => expect(api.patch).toHaveBeenCalled())
    const [url, body] = api.patch.mock.calls[0]
    expect(url).toBe('/api/v2/residents/7/apartments/11')
    expect(JSON.parse(JSON.stringify(body))).toEqual({ is_owner: true })
  })

  it('отказ по привязке шлёт комментарий', async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useRejectBinding(7), { wrapper })

    result.current.mutate({ uaId: 11, comment: 'нет документов' })

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith(
      '/api/v2/residents/7/apartments/11/reject', { comment: 'нет документов' },
    )
  })

  it('отвязка идёт DELETE-ом по вложенному пути', async () => {
    const { wrapper } = setup()
    const { result } = renderHook(() => useRemoveBinding(7), { wrapper })

    result.current.mutate(11)

    await waitFor(() => expect(api.delete).toHaveBeenCalled())
    expect(api.delete).toHaveBeenCalledWith('/api/v2/residents/7/apartments/11')
  })

  it('успешная мутация сбрасывает ВСЕ связанные кэши, включая адресные', async () => {
    const { wrapper, invalidated } = setup()
    const { result } = renderHook(() => useRemoveBinding(7), { wrapper })

    result.current.mutate(11)

    await waitFor(() => expect(invalidated.length).toBeGreaterThan(0))
    const heads = invalidated.map(k => k[0])
    for (const key of EXPECTED_KEYS) {
      expect(heads, `не сброшен кэш '${key}'`).toContain(key)
    }
    expect(invalidated).toContainEqual(['resident', 7])
  })

  it('ошибка сервера не роняет хук — мутация просто заканчивается ошибкой', async () => {
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('conflict'), { response: { status: 409 } }),
    )
    const { wrapper } = setup()
    const { result } = renderHook(() => useApproveResident(7), { wrapper })

    result.current.mutate({})

    await waitFor(() => expect(result.current.isError).toBe(true))
  })

  it('отказ правила доступа переводится по коду, а не русским detail', async () => {
    // UZ-интерфейс: detail бэка русский, X-Error-Code — машинный код.
    await i18n.changeLanguage('uz')
    try {
      api.post.mockRejectedValueOnce(Object.assign(new Error('conflict'), {
        response: {
          status: 409,
          headers: { 'x-error-code': 'phone_required' },
          data: { detail: 'Нельзя одобрить без телефона — запросите номер у жителя' },
        },
      }))
      const { wrapper } = setup()
      const { result } = renderHook(() => useApproveResident(7), { wrapper })
      result.current.mutate({})
      await waitFor(() => expect(result.current.isError).toBe(true))

      const opts = vi.mocked(toast.error).mock.calls.at(-1)?.[1] as { description: string }
      expect(opts.description).toBe(i18n.t('residents.refusal.phone_required'))
      expect(opts.description).not.toMatch(/телефон/)
    } finally {
      await i18n.changeLanguage('ru')
    }
  })

  it('разблокировка в pending — свой тост: житель вернулся к регистрации', async () => {
    api.post.mockResolvedValueOnce({ data: { id: 7, status: 'pending' } })
    const { wrapper } = setup()
    const { result } = renderHook(() => useUnblockResident(7), { wrapper })
    result.current.mutate()
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(vi.mocked(toast.success)).toHaveBeenLastCalledWith(
      i18n.t('residents.toast.unblockedToPending'))
  })
})
