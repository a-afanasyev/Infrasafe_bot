import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../test/test-utils'
import EmployeeDetailPage from './EmployeeDetailPage'
import type { EmployeeDetail } from '../types/api'

const { detailQuery, renameSpy } = vi.hoisted(() => ({
  detailQuery: { data: undefined as EmployeeDetail | undefined, isLoading: false, isError: false },
  renameSpy: vi.fn(),
}))

vi.mock('../hooks/useEmployees', () => ({
  useEmployee: () => detailQuery,
  useRenameEmployee: () => ({ mutate: renameSpy, isPending: false }),
  useToggleMeterEntry: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return { ...actual, useParams: () => ({ id: '17' }), useNavigate: () => vi.fn() }
})

function makeEmployee(over: Partial<EmployeeDetail> = {}): EmployeeDetail {
  return {
    id: 17,
    first_name: 'Пётр',
    last_name: 'Петров',
    phone: '+998901112233',
    specialization: ['plumber'],
    active_shift_id: null,
    active_shift: null,
    verification_status: 'verified',
    status: 'approved',
    roles: ['executor'],
    total_shifts: 3,
    total_completed: 12,
    rating: 4.5,
    ...over,
  } as EmployeeDetail
}

beforeEach(() => {
  renameSpy.mockClear()
  detailQuery.data = makeEmployee()
  detailQuery.isLoading = false
  detailQuery.isError = false
})

describe('EmployeeDetailPage — исправление ФИО', () => {
  it('карточка предлагает исправить ФИО', () => {
    render(<EmployeeDetailPage />)
    expect(screen.getByRole('button', { name: 'Исправить ФИО' })).toBeInTheDocument()
  })

  it('форма предзаполнена текущим ФИО', async () => {
    const user = userEvent.setup()
    render(<EmployeeDetailPage />)
    await user.click(screen.getByRole('button', { name: 'Исправить ФИО' }))
    expect(screen.getByLabelText('ФИО')).toHaveValue('Пётр Петров')
  })

  it('шлёт исправленное ФИО', async () => {
    const user = userEvent.setup()
    render(<EmployeeDetailPage />)
    await user.click(screen.getByRole('button', { name: 'Исправить ФИО' }))

    const field = screen.getByLabelText('ФИО')
    await user.clear(field)
    await user.type(field, 'Петров Пётр Петрович')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(renameSpy).toHaveBeenCalledTimes(1)
    expect(renameSpy.mock.calls[0][0]).toBe('Петров Пётр Петрович')
  })

  it('у заблокированного сотрудника правка ФИО тоже доступна', () => {
    // Блокировка — про доступ, а не про данные: опечатку исправлять всё равно
    // надо, иначе человека не найти поиском.
    detailQuery.data = makeEmployee({ status: 'blocked' })
    render(<EmployeeDetailPage />)
    expect(screen.getByRole('button', { name: 'Исправить ФИО' })).toBeEnabled()
  })
})
