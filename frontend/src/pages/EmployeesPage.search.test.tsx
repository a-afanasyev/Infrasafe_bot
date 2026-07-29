import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { waitFor } from '@testing-library/react'
import { render, screen } from '../test/test-utils'
import { TopbarProvider } from '../contexts/TopbarContext'
import { useTopbar } from '../contexts/topbar'
import EmployeesPage from './EmployeesPage'

// Тот же дефект, что чинили в «Жителях» (`docs/bugs-2026-07-28.md`, BUG-2):
// поле поиска в топбаре было контролируемым и теряло символы. «Сотрудники» —
// страница, на которой дефект был воспроизведён в живом браузере, то есть он
// тут ПРЕДСУЩЕСТВУЮЩИЙ, а не привнесённый разделом «Жители».
//
// Обычный тест страницы это не ловит: без TopbarProvider поле вообще не
// рендерится. ⚠ Саму потерю символов jsdom не воспроизводит (`act()` схлопывает
// оба коммита) — реальный guard здесь debounce: старая реализация звала
// setSearch на каждое нажатие, и тест ниже на ней падает.

const { employeesSpy } = vi.hoisted(() => ({ employeesSpy: vi.fn() }))

vi.mock('../hooks/useEmployees', () => ({
  useEmployees: (...args: unknown[]) => {
    employeesSpy(...args)
    return { data: [], isLoading: false, isError: false }
  },
  useEmployee: () => ({ data: undefined }),
  usePendingStaff: () => ({ data: [] }),
  useApproveEmployee: () => ({ mutate: vi.fn() }),
  useToggleMeterEntry: () => ({ mutate: vi.fn() }),
  useRejectEmployee: () => ({ mutate: vi.fn() }),
  useBlockEmployee: () => ({ mutate: vi.fn() }),
  useUnblockEmployee: () => ({ mutate: vi.fn() }),
  useActiveRequestsCount: () => ({ data: 0 }),
  useActivateEmployee: () => ({ mutate: vi.fn() }),
  useDeclineEmployee: () => ({ mutate: vi.fn() }),
  useCreateInvite: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteEmployee: () => ({ mutate: vi.fn() }),
}))

function TopbarStub() {
  const { actions } = useTopbar()
  return <header>{actions}</header>
}

function renderWithTopbar() {
  return render(
    <TopbarProvider>
      <TopbarStub />
      <EmployeesPage />
    </TopbarProvider>,
  )
}

beforeEach(() => employeesSpy.mockClear())

describe('EmployeesPage — поиск в топбаре', () => {
  it('принимает ввод целиком', async () => {
    const user = userEvent.setup()
    renderWithTopbar()

    const input = screen.getByRole('textbox') as HTMLInputElement
    await user.type(input, 'админ')

    expect(input.value).toBe('админ')
  })

  it('шлёт запрос один раз после паузы, а не на каждое нажатие', async () => {
    const user = userEvent.setup()
    renderWithTopbar()
    const before = employeesSpy.mock.calls.length

    await user.type(screen.getByRole('textbox'), 'админ')

    // До истечения debounce поисковый терм в запрос ещё не ушёл.
    const mid = employeesSpy.mock.calls.slice(before)
    expect(mid.every(c => c[1] === undefined)).toBe(true)

    await waitFor(() => {
      const last = employeesSpy.mock.calls[employeesSpy.mock.calls.length - 1]
      expect(last[1]).toBe('админ')
    })
  })
})
