import { describe, it, expect, beforeEach, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { useWorkReportsWebSocket } from './useWorkReports'

// Тик автопубликатора (бот, раз в 10 мин) шлёт `work_reports.updated` в канал
// канбана — страница отчётов должна перезапросить списки сама.

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

describe('useWorkReportsWebSocket', () => {
  it('подписывается на канал канбана', () => {
    const { wrapper } = setup()
    renderHook(() => useWorkReportsWebSocket(), { wrapper })
    expect(captured.endpoint).toBe('kanban')
  })

  it('событие тика сбрасывает списки отчётов', () => {
    const { wrapper, invalidated } = setup()
    renderHook(() => useWorkReportsWebSocket(), { wrapper })

    captured.handler!({ type: 'work_reports.updated', data: { published: 1 } })

    expect(invalidated).toContainEqual(['work-reports'])
  })

  it('события заявок игнорируются', () => {
    const { wrapper, invalidated } = setup()
    renderHook(() => useWorkReportsWebSocket(), { wrapper })

    captured.handler!({ type: 'request.status_changed', data: {} })

    expect(invalidated).toEqual([])
  })
})
