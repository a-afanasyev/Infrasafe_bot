import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../test/test-utils'
import EmployeeDetailPage from './EmployeeDetailPage'
import type { EmployeeDetail } from '../types/api'

const { detailQuery, renameSpy, simpleModeSpy, languageSpy } = vi.hoisted(() => ({
  detailQuery: { data: undefined as EmployeeDetail | undefined, isLoading: false, isError: false },
  renameSpy: vi.fn(),
  simpleModeSpy: vi.fn(),
  languageSpy: vi.fn(),
}))

vi.mock('../hooks/useEmployees', () => ({
  useEmployee: () => detailQuery,
  useRenameEmployee: () => ({ mutate: renameSpy, isPending: false }),
  useToggleMeterEntry: () => ({ mutate: vi.fn(), isPending: false }),
  useToggleSimpleMode: () => ({ mutate: simpleModeSpy, isPending: false }),
  useSetEmployeeLanguage: () => ({ mutate: languageSpy, isPending: false }),
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
    bot_blocked: false,
    simple_mode: false,
    language: 'ru',
    ...over,
  } as EmployeeDetail
}

beforeEach(() => {
  renameSpy.mockClear()
  simpleModeSpy.mockClear()
  languageSpy.mockClear()
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

describe('EmployeeDetailPage — простой режим исполнителя', () => {
  it('переключатель включает простой режим исполнителю', async () => {
    const user = userEvent.setup()
    render(<EmployeeDetailPage />)
    const toggle = screen.getByRole('switch', { name: 'Простой режим' })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    await user.click(toggle)
    expect(simpleModeSpy).toHaveBeenCalledWith(true)
  })

  it('включённый режим выключается и виден бейджем в шапке', async () => {
    const user = userEvent.setup()
    detailQuery.data = makeEmployee({ simple_mode: true })
    render(<EmployeeDetailPage />)
    expect(screen.getByTestId('simple-mode-badge')).toHaveTextContent('Простой режим')
    const toggle = screen.getByRole('switch', { name: 'Простой режим' })
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    await user.click(toggle)
    expect(simpleModeSpy).toHaveBeenCalledWith(false)
  })

  it('без простого режима бейджа нет', () => {
    render(<EmployeeDetailPage />)
    expect(screen.queryByTestId('simple-mode-badge')).not.toBeInTheDocument()
  })

  it('выбор языка шлёт PATCH с кодом языка', async () => {
    const user = userEvent.setup()
    render(<EmployeeDetailPage />)
    const select = screen.getByLabelText('Язык бота и Mini App')
    expect(select).toHaveValue('ru')
    await user.selectOptions(select, 'uz_cyrl')
    expect(languageSpy).toHaveBeenCalledWith('uz_cyrl')
  })

  it.each([
    ['менеджер', ['manager']],
    ['админ', ['admin', 'executor']],
    ['менеджер-исполнитель', ['manager', 'executor']],
    ['обходчик', ['inspector']],
  ])('%s — контролов нет', (_label, roles) => {
    detailQuery.data = makeEmployee({ roles })
    render(<EmployeeDetailPage />)
    expect(screen.queryByRole('switch', { name: 'Простой режим' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Язык бота и Mini App')).not.toBeInTheDocument()
  })

  it('обходчик с уже включённым режимом видит переключатель, чтобы выключить', async () => {
    const user = userEvent.setup()
    detailQuery.data = makeEmployee({ roles: ['inspector'], simple_mode: true })
    render(<EmployeeDetailPage />)
    const toggle = screen.getByRole('switch', { name: 'Простой режим' })
    await user.click(toggle)
    expect(simpleModeSpy).toHaveBeenCalledWith(false)
  })
})
