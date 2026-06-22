import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor } from '@testing-library/react'
import { renderHook } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { useReassignShift } from './useShifts'

// REG-02: прямой менеджерский reassign смены. Хук шлёт executor_id на
// POST /shifts/{id}/reassign и инвалидирует кэши (включая ['shift', id]).

describe('useReassignShift', () => {
  it('POSTs executor_id to /shifts/{id}/reassign and resolves', async () => {
    let body: Record<string, unknown> | null = null
    let calledId: string | null = null
    server.use(
      http.post('*/api/v2/shifts/:id/reassign', async ({ request, params }) => {
        calledId = String(params.id)
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 42, user_id: 9, status: 'active' })
      }),
    )
    const { result } = renderHook(() => useReassignShift())
    result.current.mutate({ id: 42, executor_id: 9 })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(calledId).toBe('42')
    expect(body).toEqual({ executor_id: 9 })
  })

  it('reports an error on a 409 overlap', async () => {
    server.use(
      http.post('*/api/v2/shifts/:id/reassign', () => new HttpResponse(null, { status: 409 })),
    )
    const { result } = renderHook(() => useReassignShift())
    result.current.mutate({ id: 7, executor_id: 3 })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
