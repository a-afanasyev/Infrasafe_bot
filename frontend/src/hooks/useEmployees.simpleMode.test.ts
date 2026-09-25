import { describe, it, expect, vi, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor } from '@testing-library/react'
import { renderHook } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { useSetEmployeeLanguage, useToggleSimpleMode } from './useEmployees'

// Простой режим исполнителя (Фаза 2): менеджер включает панель и язык из
// карточки сотрудника. Отказ бэка (403/422) показываем понятным текстом —
// сырой английский detail поддержке ничего не скажет.
const { toastSuccess, toastError } = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))

beforeEach(() => {
  toastSuccess.mockClear()
  toastError.mockClear()
})

describe('useToggleSimpleMode', () => {
  it('шлёт PATCH simple-mode с enabled и показывает тост успеха', async () => {
    let body: unknown
    server.use(
      http.patch('*/api/v2/shifts/employees/17/simple-mode', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 17, simple_mode: true })
      }),
    )
    const { result } = renderHook(() => useToggleSimpleMode(17))
    result.current.mutate(true)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toEqual({ enabled: true })
    expect(toastSuccess).toHaveBeenCalledWith('Простой режим включён')
  })

  it('403 — понятный текст вместо сырого detail', async () => {
    server.use(
      http.patch('*/api/v2/shifts/employees/17/simple-mode', () =>
        HttpResponse.json(
          { detail: 'Cannot change simple mode of a manager or admin user' },
          { status: 403 },
        ),
      ),
    )
    const { result } = renderHook(() => useToggleSimpleMode(17))
    result.current.mutate(true)
    await waitFor(() => expect(result.current.isError).toBe(true))
    const [title, opts] = toastError.mock.calls[0]
    expect(title).toBe('Не удалось изменить простой режим')
    expect(opts.description).toBe('Менеджерам и администраторам эта настройка недоступна')
    expect(JSON.stringify(toastError.mock.calls)).not.toContain('Cannot change')
  })

  it('422 — «только исполнителям»', async () => {
    server.use(
      http.patch('*/api/v2/shifts/employees/17/simple-mode', () =>
        HttpResponse.json({ detail: 'Simple mode is available only for executors' }, { status: 422 }),
      ),
    )
    const { result } = renderHook(() => useToggleSimpleMode(17))
    result.current.mutate(true)
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toastError.mock.calls[0][1].description).toBe('Простой режим доступен только исполнителям')
  })
})

describe('useSetEmployeeLanguage', () => {
  it('шлёт PATCH language и показывает тост успеха', async () => {
    let body: unknown
    server.use(
      http.patch('*/api/v2/shifts/employees/17/language', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 17, language: 'uz_cyrl' })
      }),
    )
    const { result } = renderHook(() => useSetEmployeeLanguage(17))
    result.current.mutate('uz_cyrl')
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toEqual({ language: 'uz_cyrl' })
    expect(toastSuccess).toHaveBeenCalledWith('Язык сотрудника изменён')
  })

  it('422 — «только сотруднику», без сырого detail', async () => {
    server.use(
      http.patch('*/api/v2/shifts/employees/17/language', () =>
        HttpResponse.json({ detail: 'Not a staff account (manager/executor/inspector)' }, { status: 422 }),
      ),
    )
    const { result } = renderHook(() => useSetEmployeeLanguage(17))
    result.current.mutate('uz')
    await waitFor(() => expect(result.current.isError).toBe(true))
    const [title, opts] = toastError.mock.calls[0]
    expect(title).toBe('Не удалось изменить язык')
    expect(opts.description).toBe('Язык можно изменить только сотруднику')
  })

  it('прочая ошибка — без description (detail не показываем)', async () => {
    server.use(
      http.patch('*/api/v2/shifts/employees/17/language', () =>
        HttpResponse.json({ detail: 'Internal boom' }, { status: 500 }),
      ),
    )
    const { result } = renderHook(() => useSetEmployeeLanguage(17))
    result.current.mutate('ru')
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toastError.mock.calls[0][1]).toBeUndefined()
  })
})
