import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen, within } from '../../test/test-utils'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import StaffTable from './StaffTable'
import PendingApprovalCard from './PendingApprovalCard'

// TEST-068 (порция employees): табличный вид сотрудников и карточка ожидающего
// одобрения — чистый рендер по данным, действия через колбэки.

function emp(overrides: Partial<EmployeeBrief> = {}): EmployeeBrief {
  return {
    id: 1, first_name: 'Андрей', last_name: 'Афанасьев', phone: '+998901112233',
    specialization: ['electrician'], active_shift_id: 44, verification_status: 'verified',
    status: 'approved', roles: ['executor'], bot_blocked: false, ...overrides,
  }
}

const noop = () => {}

describe('StaffTable', () => {
  it('пустой список — EmptyState без таблицы', () => {
    render(<StaffTable employees={[]} onAssign={noop} onBlock={noop} onDelete={noop} isBlockPending={false} />)
    expect(screen.getByText('Сотрудники не найдены')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('верифицированный на смене: бейджи, «Назначить», «Блок», «Удалить» зовут колбэки', async () => {
    const user = userEvent.setup()
    const onAssign = vi.fn(); const onBlock = vi.fn(); const onDelete = vi.fn()
    const e = emp({ roles: ['executor', 'manager'] })
    render(<StaffTable employees={[e]} onAssign={onAssign} onBlock={onBlock} onDelete={onDelete} isBlockPending={false} />)

    const row = screen.getByRole('row', { name: /Андрей Афанасьев/ })
    expect(within(row).getByText('Менеджер')).toBeInTheDocument()
    expect(within(row).getByText('+998901112233')).toBeInTheDocument()
    expect(within(row).getByText('✓ Верифицирован')).toBeInTheDocument()
    expect(within(row).getByText('● На смене')).toBeInTheDocument()
    expect(within(row).getByText('#44')).toBeInTheDocument()

    await user.click(within(row).getByRole('button', { name: 'Назначить' }))
    await user.click(within(row).getByRole('button', { name: 'Блок' }))
    await user.click(within(row).getByRole('button', { name: 'Удалить' }))
    expect(onAssign).toHaveBeenCalledWith(e)
    expect(onBlock).toHaveBeenCalledWith(e)
    expect(onDelete).toHaveBeenCalledWith(e)
  })

  it('на проверке и не на смене: нет «Назначить», прочерки по спецу/смене', () => {
    render(<StaffTable employees={[emp({ verification_status: 'pending', active_shift_id: null, specialization: [] })]}
                       onAssign={noop} onBlock={noop} onDelete={noop} isBlockPending={false} />)
    expect(screen.getByText('⏳ На проверке')).toBeInTheDocument()
    expect(screen.getByText('● Не на смене')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Назначить' })).not.toBeInTheDocument()
    expect(screen.getAllByText('—')).toHaveLength(2)
  })

  it('заблокированный: бейдж и «Разблок» (заблокирована при isBlockPending)', () => {
    const { rerender } = render(<StaffTable employees={[emp({ status: 'blocked' })]}
                                             onAssign={noop} onBlock={noop} onDelete={noop} isBlockPending={false} />)
    expect(screen.getByText('Заблокирован')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Разблок' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Блок' })).not.toBeInTheDocument()

    rerender(<StaffTable employees={[emp({ status: 'blocked' })]}
                         onAssign={noop} onBlock={noop} onDelete={noop} isBlockPending />)
    expect(screen.getByRole('button', { name: 'Разблок' })).toBeDisabled()
  })

  it('сортировка: заголовки с serverField кликабельны и зовут toggle', async () => {
    const user = userEvent.setup()
    const sort = {
      direction: vi.fn(() => null), ariaSort: vi.fn(() => 'none' as const), toggle: vi.fn(),
    } as unknown as NonNullable<Parameters<typeof StaffTable>[0]['sort']>
    render(<StaffTable employees={[emp()]} onAssign={noop} onBlock={noop} onDelete={noop} isBlockPending={false} sort={sort} />)
    const header = screen.getAllByRole('columnheader')[0]
    await user.click(within(header).getByRole('button'))
    expect(sort.toggle).toHaveBeenCalled()
  })
})

describe('PendingApprovalCard', () => {
  it('имя, роль по приоритету (manager > executor), телефон, спец; кнопки зовут колбэки с id', async () => {
    const user = userEvent.setup()
    const onApprove = vi.fn(); const onReject = vi.fn()
    render(<PendingApprovalCard employee={emp({ id: 7, roles: ['applicant', 'executor', 'manager'] })}
                                onApprove={onApprove} onReject={onReject} />)
    expect(screen.getByText('Андрей Афанасьев')).toBeInTheDocument()
    expect(screen.getByText('Менеджер')).toBeInTheDocument()
    expect(screen.getByText('+998901112233')).toBeInTheDocument()
    expect(screen.getByText('Ожидают одобрения')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Одобрить' }))
    await user.click(screen.getByRole('button', { name: 'Отклонить' }))
    expect(onApprove).toHaveBeenCalledWith(7)
    expect(onReject).toHaveBeenCalledWith(7)
  })

  it('isPending блокирует обе кнопки; без имени — «Без имени»', () => {
    render(<PendingApprovalCard employee={emp({ first_name: null, last_name: null, roles: [] })}
                                onApprove={noop} onReject={noop} isPending />)
    expect(screen.getByText('Без имени')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Одобрить' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Отклонить' })).toBeDisabled()
  })
})
