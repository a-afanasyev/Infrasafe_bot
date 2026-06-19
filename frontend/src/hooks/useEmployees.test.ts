import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor } from '@testing-library/react'
import { renderHook } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import {
  useEmployees,
  useEmployee,
  useApproveEmployee,
} from './useEmployees'

// TEST-068 Phase 2: data-hooks over MSW. Per-test handlers via server.use keep
// the global handlers.ts lean (Phase 3 widens it). renderHook from test-utils
// supplies a fresh QueryClient (retry:false) so failures surface fast.

describe('useEmployees', () => {
  it('fetches the employee list', async () => {
    server.use(
      http.get('*/api/v2/shifts/employees', () =>
        HttpResponse.json([
          { id: 1, first_name: 'A', last_name: 'B', role: 'executor' },
          { id: 2, first_name: 'C', last_name: 'D', role: 'executor' },
        ]),
      ),
    )
    const { result } = renderHook(() => useEmployees())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(2)
    expect(result.current.data?.[0].first_name).toBe('A')
  })

  it('surfaces a server error', async () => {
    server.use(
      http.get('*/api/v2/shifts/employees', () => new HttpResponse(null, { status: 500 })),
    )
    const { result } = renderHook(() => useEmployees())
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})

describe('useEmployee — enabled gating', () => {
  it('does not fetch while id is null', () => {
    // No handler registered: onUnhandledRequest:"error" would fail if it fetched.
    const { result } = renderHook(() => useEmployee(null))
    // Disabled query (enabled:false) stays pending with no in-flight fetch.
    expect(result.current.fetchStatus).toBe('idle')
    expect(result.current.data).toBeUndefined()
  })

  it('fetches once an id is provided', async () => {
    server.use(
      http.get('*/api/v2/shifts/employees/5', () =>
        HttpResponse.json({ id: 5, first_name: 'E', last_name: 'F', role: 'executor' }),
      ),
    )
    const { result } = renderHook(() => useEmployee(5))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.id).toBe(5)
  })
})

describe('useApproveEmployee — mutation', () => {
  it('resolves on a successful PATCH', async () => {
    server.use(
      http.patch('*/api/v2/shifts/employees/3/approve', () => HttpResponse.json({ ok: true })),
    )
    const { result } = renderHook(() => useApproveEmployee())
    result.current.mutate(3)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it('reports an error on a failed PATCH', async () => {
    server.use(
      http.patch('*/api/v2/shifts/employees/3/approve', () => new HttpResponse(null, { status: 400 })),
    )
    const { result } = renderHook(() => useApproveEmployee())
    result.current.mutate(3)
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
