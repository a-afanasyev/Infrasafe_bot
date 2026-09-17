import { describe, it, expect } from 'vitest'
import { act, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { renderHook } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { useEmployeePicker } from './useEmployeePicker'

// AUD7-CODE-06: пикеры сотрудников (смены, переназначение, удаление) раньше
// брали первые 50 записей без поиска — 51-го выбрать было нельзя. Теперь
// пикер ходит за широкой страницей и передаёт поиск серверу.

function employees(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    first_name: `Имя${i + 1}`,
    last_name: `Фамилия${i + 1}`,
    role: 'executor',
    status: 'approved',
  }))
}

describe('useEmployeePicker', () => {
  it('запрашивает широкую страницу и отдаёт всех, включая 51-го и последнего', async () => {
    let url: URL | undefined
    server.use(
      http.get('*/api/v2/shifts/employees', ({ request }) => {
        url = new URL(request.url)
        return HttpResponse.json(employees(120), { headers: { 'X-Total-Count': '120' } })
      }),
    )
    const { result } = renderHook(() => useEmployeePicker())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(Number(url?.searchParams.get('limit'))).toBeGreaterThanOrEqual(120)
    expect(result.current.employees.map(e => e.id)).toContain(51)
    expect(result.current.employees.at(-1)?.id).toBe(120)
    expect(result.current.truncated).toBe(false)
  })

  it('передаёт поиск серверу (после паузы ввода) и не фильтрует на клиенте', async () => {
    const seen: string[] = []
    server.use(
      http.get('*/api/v2/shifts/employees', ({ request }) => {
        const u = new URL(request.url)
        seen.push(u.searchParams.get('search') ?? '')
        return HttpResponse.json(u.searchParams.get('search') ? employees(1) : employees(3), {
          headers: { 'X-Total-Count': u.searchParams.get('search') ? '1' : '3' },
        })
      }),
    )
    const { result } = renderHook(() => useEmployeePicker({ verification_status: 'verified' }))
    await waitFor(() => expect(result.current.employees).toHaveLength(3))

    act(() => result.current.setSearch('Иван'))
    await waitFor(() => expect(result.current.employees).toHaveLength(1))
    expect(seen).toContain('Иван')
  })

  it('сообщает об усечении, когда сотрудников больше страницы', async () => {
    server.use(
      http.get('*/api/v2/shifts/employees', () =>
        HttpResponse.json(employees(200), { headers: { 'X-Total-Count': '350' } }),
      ),
    )
    const { result } = renderHook(() => useEmployeePicker())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.truncated).toBe(true)
    expect(result.current.total).toBe(350)
  })
})
