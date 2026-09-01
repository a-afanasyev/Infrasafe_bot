import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { waitFor } from '@testing-library/react'
import { render, screen } from '../test/test-utils'
import EmployeesPage from './EmployeesPage'
import type { EmployeeBrief } from '../types/api'

// Кнопка «Верифицировать» в карточке сотрудника НЕ РАБОТАЛА: StaffCard зовёт
// `onVerify?.(employee)`, а страница этот проп не передавала вовсе —
// опциональная цепочка делала клик пустым. Ни запроса, ни ошибки, ни тоста:
// менеджер жмёт и не понимает, почему ничего не происходит (профиль сотрудника
// на проде так и висел `verification_status='pending'`).
//
// Тест держит именно СВЯЗКУ «клик → мутация». Проверять сам StaffCard
// бесполезно: он-то как раз исправен, дефект жил в месте его подключения.

const UNVERIFIED: EmployeeBrief = {
  id: 17,
  first_name: 'Test',
  last_name: 'del please',
  phone: null,
  specialization: ['plumber'],
  active_shift_id: null,
  verification_status: 'pending',
  status: 'pending',
  roles: ['applicant', 'executor'],
  bot_blocked: false,
}

const { approveSpy } = vi.hoisted(() => ({ approveSpy: vi.fn() }))

vi.mock('../hooks/useEmployees', () => ({
  useEmployees: () => ({ data: [UNVERIFIED], isLoading: false, isError: false }),
  useEmployee: () => ({ data: undefined }),
  usePendingStaff: () => ({ data: [] }),
  useApproveEmployee: () => ({ mutate: approveSpy, isPending: false }),
  useToggleMeterEntry: () => ({ mutate: vi.fn() }),
  useBlockEmployee: () => ({ mutate: vi.fn() }),
  useUnblockEmployee: () => ({ mutate: vi.fn() }),
  useActiveRequestsCount: () => ({ data: 0 }),
  useActivateEmployee: () => ({ mutate: vi.fn() }),
  useDeclineEmployee: () => ({ mutate: vi.fn() }),
  useCreateInvite: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteEmployee: () => ({ mutate: vi.fn() }),
  useRequestEmployeePhone: () => ({ mutate: vi.fn(), isPending: false, isSuccess: false }),
}))

beforeEach(() => approveSpy.mockClear())

describe('EmployeesPage — кнопка «Верифицировать»', () => {
  it('шлёт верификацию по id сотрудника', async () => {
    const user = userEvent.setup()
    render(<EmployeesPage />)

    const button = await screen.findByRole('button', { name: 'Верифицировать' })
    await user.click(button)

    await waitFor(() => expect(approveSpy).toHaveBeenCalledWith(17))
  })

  it('у верифицированного вместо неё кнопка назначения', async () => {
    vi.resetModules()
    render(<EmployeesPage />)

    // Карточка неверифицированного показывает «Верифицировать», а не «Назначить»
    expect(await screen.findByRole('button', { name: 'Верифицировать' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Назначить' })).not.toBeInTheDocument()
  })
})
