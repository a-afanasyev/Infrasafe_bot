import { describe, it, expect, beforeEach, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { useResidentsWebSocket } from './useResidents'

// WS — ускоритель поверх polling'а, а не замена ему, поэтому проверяется одно:
// на событие привязки сбрасываются ТЕ ЖЕ кэши, что и после собственной
// мутации. Если списки расходятся, менеджер увидит одно на своём экране и
// другое — после действия коллеги.

const captured = vi.hoisted(() => ({
  endpoint: null as string | null,
  handler: null as ((e: { type: string; data: unknown }) => void) | null,
}))

vi.mock('./useWebSocket', () => ({
  useWebSocket: (endpoint: string, onMessage: (e: { type: string; data: unknown }) => void) => {
    captured.endpoint = endpoint
    captured.handler = onMessage
  },
}))

const EXPECTED_KEYS = [
  'residents', 'resident', 'residents-stats',
  'moderation', 'address-stats',
  'apartment-detail', 'apartments', 'all-apartments',
]

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
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
  captured.endpoint = null
  captured.handler = null
})

describe('useResidentsWebSocket', () => {
  it('подписывается на канал квартир', () => {
    const { wrapper } = setup()
    renderHook(() => useResidentsWebSocket(), { wrapper })
    expect(captured.endpoint).toBe('apartments')
  })

  it('событие привязки сбрасывает тот же набор кэшей, что и мутация', () => {
    const { wrapper, invalidated } = setup()
    renderHook(() => useResidentsWebSocket(), { wrapper })

    captured.handler!({ type: 'apartment_request.approved', data: {} })

    const heads = invalidated.map(k => k[0])
    for (const key of EXPECTED_KEYS) {
      expect(heads, `не сброшен кэш '${key}'`).toContain(key)
    }
  })

  it('чужие события игнорируются', () => {
    const { wrapper, invalidated } = setup()
    renderHook(() => useResidentsWebSocket(), { wrapper })

    captured.handler!({ type: 'building.updated', data: {} })
    captured.handler!({ type: 'yard.created', data: {} })

    expect(invalidated).toEqual([])
  })

  it('событие удаления привязки тоже учитывается', () => {
    const { wrapper, invalidated } = setup()
    renderHook(() => useResidentsWebSocket(), { wrapper })

    captured.handler!({ type: 'apartment_request.removed', data: {} })
    expect(invalidated.length).toBeGreaterThan(0)
  })
})
