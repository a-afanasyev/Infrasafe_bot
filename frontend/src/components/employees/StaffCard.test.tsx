import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../test/test-utils'
import StaffCard from './StaffCard'
import { useNameCaseStore } from '../../stores/nameCaseStore'
import { apiClient } from '../../api/client'
import type { EmployeeBrief } from '../../hooks/useEmployees'

/**
 * Оптимизация читаемости плиток (жалоба владельца 2026-08-27): КАПС-ФИО из БД
 * обрезался в одну строку, а абсолютный бейдж «Верифицирован» наезжал на имя.
 * Теперь имя рендерится Видом Имени и до двух строк, бейджи — в потоке.
 */

function makeEmployee(overrides: Partial<EmployeeBrief> = {}): EmployeeBrief {
  return {
    id: 1,
    first_name: 'KASIMOV TALGAT',
    last_name: 'MANSUROVICH',
    phone: '+998901234567',
    specialization: ['electrician'],
    active_shift_id: 44,
    verification_status: 'verified',
    status: 'approved',
    roles: ['executor'],
    bot_blocked: false,
    ...overrides,
  }
}

describe('StaffCard — бейдж «Бот заблокирован»', () => {
  it('показывается при bot_blocked', () => {
    render(<StaffCard employee={makeEmployee({ bot_blocked: true })} />)
    expect(screen.getByText(/Бот заблокирован/)).toBeInTheDocument()
  })

  it('нет бейджа без блокировки', () => {
    render(<StaffCard employee={makeEmployee()} />)
    expect(screen.queryByText(/Бот заблокирован/)).not.toBeInTheDocument()
  })
})

describe('StaffCard', () => {
  beforeEach(() => useNameCaseStore.setState({ mode: 'title' }))

  it('ФИО показывается Видом Имени, бейдж верификации и специализация на месте', () => {
    render(<StaffCard employee={makeEmployee()} />)
    expect(screen.getByText('Kasimov Talgat Mansurovich')).toBeInTheDocument()
    expect(screen.getByText(/Верифицирован/)).toBeInTheDocument()
    expect(screen.getByText('Электрика')).toBeInTheDocument()
  })

  it('режим «ФИО заглавными» — имя капсом, бейджи не тронуты', () => {
    useNameCaseStore.setState({ mode: 'caps' })
    render(<StaffCard employee={makeEmployee({ first_name: 'Kasimov Talgat' })} />)
    expect(screen.getByText('KASIMOV TALGAT MANSUROVICH')).toBeInTheDocument()
    expect(screen.getByText(/Верифицирован/)).toBeInTheDocument()
  })

  it('заблокированный: бейдж «Заблокирован» рядом с верификацией, оба в потоке', () => {
    render(<StaffCard employee={makeEmployee({ status: 'blocked' })} />)
    expect(screen.getByText(/Заблокирован/)).toBeInTheDocument()
  })
})

describe('StaffCard — запрос номера телефона', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('без телефона — кнопка «Запросить номер», клик шлёт запрос в API', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { sent: true } })
    render(<StaffCard employee={makeEmployee({ phone: null })} />)

    const btn = screen.getByRole('button', { name: /Запросить номер/ })
    fireEvent.click(btn)

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/api/v2/shifts/employees/1/request-phone'))
  })

  it('с телефоном кнопки нет — показан сам номер', () => {
    render(<StaffCard employee={makeEmployee()} />)
    expect(screen.getByText('+998901234567')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Запросить номер/ })).not.toBeInTheDocument()
  })
})
