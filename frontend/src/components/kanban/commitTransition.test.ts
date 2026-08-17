import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient } from '@tanstack/react-query'

import { commitTransition, applyOptimisticTransition } from './commitTransition'
import { kanbanQueryKey, KANBAN_QUERY_PREFIX } from '../../hooks/useKanban'
import { apiClient } from '../../api/client'

// AUD5-APIFE-8. Два дефекта одного места:
//  1. оптимистичное обновление писалось в ЗАХАРДКОЖЕННЫЙ ключ `['kanban', {}]`,
//     который совпадает с реальным только пока фильтров нет;
//  2. при успешном PATCH не было ни invalidate, ни применения ответа —
//     реконсиляция шла только через WS, а он может быть мёртв (AUD5-APIFE-7).
//
// Подменяется `apiClient` (HTTP-граница, уровень ниже), но НЕ сам
// `commitTransition` и НЕ `QueryClient` — иначе тест проверял бы собственный
// дублёр, как это уже случилось в PR #263.

vi.mock('../../api/client', () => ({
  apiClient: { patch: vi.fn(() => Promise.resolve({ data: {} })) },
}))

const CARD = {
  request_number: '260725-001',
  status: 'Новая',
  category: 'Сантехника',
  urgency: null,
  source: null,
  description: null,
  address: null,
  executor_id: null,
  executor_name: null,
  notes: null,
  completion_report: null,
  requested_materials: null,
  return_reason: null,
  created_at: '2026-07-25T00:00:00Z',
  updated_at: null,
  manager_confirmed: false,
}

function seed(qc: QueryClient, key: readonly unknown[]) {
  qc.setQueryData(key, {
    columns: [
      { status: 'Новая', count: 1, requests: [CARD] },
      { status: 'В работе', count: 0, requests: [] },
    ],
  })
}

let qc: QueryClient

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.mocked(apiClient.patch).mockClear()
  vi.mocked(apiClient.patch).mockResolvedValue({ data: {} })
})

describe('applyOptimisticTransition', () => {
  it('переносит карточку в целевую колонку и правит оба счётчика', () => {
    const next = applyOptimisticTransition(
      {
        columns: [
          { status: 'Новая', count: 1, requests: [CARD] },
          { status: 'В работе', count: 0, requests: [] },
        ],
      },
      '260725-001',
      'В работе',
    )
    expect(next.columns[0].requests).toHaveLength(0)
    expect(next.columns[0].count).toBe(0)
    expect(next.columns[1].requests.map(r => r.status)).toEqual(['В работе'])
    expect(next.columns[1].count).toBe(1)
  })

  it('неизвестная заявка не меняет доску', () => {
    const before = { columns: [{ status: 'Новая', count: 1, requests: [CARD] }] }
    expect(applyOptimisticTransition(before, 'нет-такой', 'В работе')).toBe(before)
  })
})

describe('commitTransition — ключ кэша', () => {
  it('пишет в ключ, который РЕАЛЬНО читает useKanban (без фильтров)', async () => {
    const key = kanbanQueryKey({})
    seed(qc, key)

    await commitTransition({
      queryClient: qc,
      queryKey: key,
      requestNumber: '260725-001',
      data: { status: 'В работе' },
      onError: () => {},
    })

    const board = qc.getQueryData<{ columns: { status: string; count: number }[] }>(key)
    expect(board?.columns.find(c => c.status === 'В работе')?.count).toBe(1)
  })

  it('пишет в ключ С фильтрами, а не в захардкоженный пустой', async () => {
    // Именно этот случай и был дефектом: при активном фильтре оптимистичное
    // обновление уходило в чужой (пустой) ключ, а доска не двигалась.
    const key = kanbanQueryKey({ category: 'Сантехника' })
    seed(qc, key)

    await commitTransition({
      queryClient: qc,
      queryKey: key,
      requestNumber: '260725-001',
      data: { status: 'В работе' },
      onError: () => {},
    })

    const board = qc.getQueryData<{ columns: { status: string; count: number }[] }>(key)
    expect(board?.columns.find(c => c.status === 'В работе')?.count).toBe(1)
    // и пустой ключ при этом не тронут
    expect(qc.getQueryData(kanbanQueryKey({}))).toBeUndefined()
  })
})

describe('commitTransition — реконсиляция с сервером', () => {
  it('УСПЕШНЫЙ PATCH инвалидирует канбан (не полагаемся на живой WS)', async () => {
    const key = kanbanQueryKey({})
    seed(qc, key)
    const invalidate = vi.spyOn(qc, 'invalidateQueries')

    await commitTransition({
      queryClient: qc,
      queryKey: key,
      requestNumber: '260725-001',
      data: { status: 'В работе' },
      onError: () => {},
    })

    expect(apiClient.patch).toHaveBeenCalledTimes(1)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: KANBAN_QUERY_PREFIX })
  })

  it('инвалидация по ПРЕФИКСУ — тогда обновятся и варианты с фильтрами', async () => {
    const key = kanbanQueryKey({ category: 'Сантехника' })
    seed(qc, key)
    const invalidate = vi.spyOn(qc, 'invalidateQueries')

    await commitTransition({
      queryClient: qc,
      queryKey: key,
      requestNumber: '260725-001',
      data: { status: 'В работе' },
      onError: () => {},
    })

    const arg = invalidate.mock.calls[0][0] as { queryKey: readonly unknown[] }
    expect(arg.queryKey).toEqual(KANBAN_QUERY_PREFIX)
    expect(arg.queryKey.length).toBeLessThan(key.length) // именно префикс, не точный ключ
  })

  it('ошибка PATCH зовёт onError и всё равно инвалидирует (откат оптимизма)', async () => {
    const key = kanbanQueryKey({})
    seed(qc, key)
    vi.mocked(apiClient.patch).mockRejectedValueOnce(new Error('422'))
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const onError = vi.fn()

    await commitTransition({
      queryClient: qc,
      queryKey: key,
      requestNumber: '260725-001',
      data: { status: 'В работе' },
      onError,
    })

    expect(onError).toHaveBeenCalledTimes(1)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: KANBAN_QUERY_PREFIX })
  })

  it('ошибка PATCH не всплывает наружу — доска не должна падать', async () => {
    const key = kanbanQueryKey({})
    seed(qc, key)
    vi.mocked(apiClient.patch).mockRejectedValueOnce(new Error('boom'))

    await expect(
      commitTransition({
        queryClient: qc,
        queryKey: key,
        requestNumber: '260725-001',
        data: { status: 'В работе' },
        onError: () => {},
      }),
    ).resolves.toBeUndefined()
  })

  it('onSuccess получает карточку из ответа PATCH', async () => {
    // Ответ раньше выбрасывался. Вызывающему он нужен, чтобы отметить заявку
    // прочитанной на той версии, которую он сам же и создал переходом:
    // `updated_at` бампается ЛЮБЫМ изменением строки, включая своё.
    const key = kanbanQueryKey({})
    seed(qc, key)
    const card = { request_number: '260725-001', updated_at: '2026-08-16T12:00:00Z' }
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: card } as never)
    const onSuccess = vi.fn()

    await commitTransition({
      queryClient: qc,
      queryKey: key,
      requestNumber: '260725-001',
      data: { status: 'Уточнение' },
      onError: () => {},
      onSuccess,
    })

    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onSuccess.mock.calls[0][0]).toMatchObject({ updated_at: '2026-08-16T12:00:00Z' })
  })

  it('onSuccess НЕ зовётся при ошибке PATCH', async () => {
    const key = kanbanQueryKey({})
    seed(qc, key)
    vi.mocked(apiClient.patch).mockRejectedValueOnce(new Error('422'))
    const onSuccess = vi.fn()

    await commitTransition({
      queryClient: qc,
      queryKey: key,
      requestNumber: '260725-001',
      data: { status: 'Уточнение' },
      onError: () => {},
      onSuccess,
    })

    expect(onSuccess).not.toHaveBeenCalled()
  })
})

describe('commitTransition: текст отказа от сервера', () => {
  it('пробрасывает detail в onError', async () => {
    vi.spyOn(apiClient, 'patch').mockRejectedValueOnce({
      response: { data: { detail: 'Нет дежурного исполнителя со специализацией plumber' } },
    })
    const onError = vi.fn()
    await commitTransition({
      queryClient: new QueryClient(),
      queryKey: ['kanban'],
      requestNumber: '260817-001',
      data: { status: 'В работе' },
      onError,
    })
    // Раньше тело ошибки выбрасывалось целиком, и осмысленный отказ
    // («нет дежурного») превращался в generic-баннер.
    expect(onError).toHaveBeenCalledWith('Нет дежурного исполнителя со специализацией plumber')
  })

  it('без detail отдаёт undefined — вызывающий покажет свой текст', async () => {
    vi.spyOn(apiClient, 'patch').mockRejectedValueOnce(new Error('network'))
    const onError = vi.fn()
    await commitTransition({
      queryClient: new QueryClient(),
      queryKey: ['kanban'],
      requestNumber: '260817-002',
      data: { status: 'В работе' },
      onError,
    })
    expect(onError).toHaveBeenCalledWith(undefined)
  })
})
