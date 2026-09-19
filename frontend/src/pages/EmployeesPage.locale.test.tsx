import { describe, it, expect, vi } from 'vitest'
import { act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { render, screen, testI18n } from '../test/test-utils'
import uz from '../i18n/locales/uz.json'
import EmployeesPage from './EmployeesPage'
import type { EmployeeBrief } from '../types/api'

// AUD8-FE-03: handleBlockToggle замыкал `t` без него в deps — после смены языка
// диалог блокировки открывался на прежнем языке.

const APPROVED: EmployeeBrief = {
  id: 21, first_name: 'Иван', last_name: 'Тестов', phone: null, specialization: ['plumber'],
  active_shift_id: null, verification_status: 'verified', status: 'approved',
  roles: ['executor'], bot_blocked: false,
}

// Стабильные объекты мутаций, как у настоящего useMutation при смене языка:
// с новым объектом на каждый рендер колбэк пересоздавался бы и баг маскировался.
const stable = vi.hoisted(() => ({
  block: { mutate: vi.fn() },
  unblock: { mutate: vi.fn() },
  noop: { mutate: vi.fn(), isPending: false, isSuccess: false },
}))

vi.mock('../hooks/useEmployees', () => ({
  useEmployeesPage: () => ({ data: { items: [APPROVED], total: 1 }, isLoading: false, isError: false }),
  useEmployee: () => ({ data: undefined }),
  usePendingStaff: () => ({ data: [] }),
  useApproveEmployee: () => stable.noop,
  useToggleMeterEntry: () => stable.noop,
  useBlockEmployee: () => stable.block,
  useUnblockEmployee: () => stable.unblock,
  useActiveRequestsCount: () => ({ data: 0 }),
  useActivateEmployee: () => stable.noop,
  useDeclineEmployee: () => stable.noop,
  useCreateInvite: () => stable.noop,
  useDeleteEmployee: () => stable.noop,
  useRequestEmployeePhone: () => stable.noop,
}))

describe('EmployeesPage — диалог блокировки после смены языка', () => {
  it('заголовок подтверждения на текущем языке, а не на том, что был при монтировании', async () => {
    testI18n.addResourceBundle('uz', 'translation', uz, true, true)
    const user = userEvent.setup()
    render(<EmployeesPage />)

    await user.click(await screen.findByRole('button', { name: 'Блок' }))
    expect(await screen.findByText('Заблокировать сотрудника')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Отмена' }))

    await act(async () => { await testI18n.changeLanguage('uz') })
    await user.click(await screen.findByRole('button', { name: 'Blok' }))
    expect(await screen.findByText('Xodimni bloklash')).toBeInTheDocument()
    expect(screen.queryByText('Заблокировать сотрудника')).toBeNull()

    await act(async () => { await testI18n.changeLanguage('ru') })
  })
})
