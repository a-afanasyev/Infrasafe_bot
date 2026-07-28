import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { within } from '@testing-library/react'
import { render, screen } from '../../test/test-utils'
import ResidentApartmentsList from './ResidentApartmentsList'
import type { ResidentApartment } from '../../types/api'

const m = vi.hoisted(() => ({
  approve: vi.fn(), reject: vi.fn(), update: vi.fn(), remove: vi.fn(),
}))

vi.mock('../../hooks/useResidents', () => ({
  useApproveBinding: () => ({ mutate: m.approve, isPending: false }),
  useRejectBinding: () => ({ mutate: m.reject, isPending: false }),
  useUpdateBinding: () => ({ mutate: m.update, isPending: false }),
  useRemoveBinding: () => ({ mutate: m.remove, isPending: false }),
}))

function binding(over: Partial<ResidentApartment> = {}): ResidentApartment {
  return {
    id: 11, apartment_id: 700, apartment_number: '42',
    building_id: 70, building_address: 'ул. Тестовая 1',
    yard_id: 7, yard_name: 'Двор-7',
    status: 'approved', is_owner: false, is_primary: true,
    requested_at: '2026-07-01T10:00:00Z', reviewed_at: null, admin_comment: null,
    ...over,
  }
}

beforeEach(() => {
  m.approve.mockClear(); m.reject.mockClear()
  m.update.mockClear(); m.remove.mockClear()
})

describe('ResidentApartmentsList', () => {
  it('у pending-привязки — модерация, у approved — редактирование', () => {
    render(<ResidentApartmentsList residentId={1} apartments={[
      binding({ id: 11, status: 'pending', is_primary: false }),
      binding({ id: 12, apartment_number: '43', status: 'approved' }),
    ]} />)

    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Отклонить' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Отметить владельцем' })).toBeInTheDocument()
  })

  it('«сделать основной» не предлагается той, что уже основная', () => {
    render(<ResidentApartmentsList residentId={1} apartments={[binding({ is_primary: true })]} />)
    expect(screen.queryByRole('button', { name: 'Сделать основной' })).not.toBeInTheDocument()
  })

  it('отказ требует причину от 3 символов и уходит без пробелов по краям', async () => {
    const user = userEvent.setup()
    render(<ResidentApartmentsList residentId={1}
                                   apartments={[binding({ status: 'pending', is_primary: false })]} />)

    await user.click(screen.getByRole('button', { name: 'Отклонить' }))
    const field = screen.getByPlaceholderText(/Причина отказа/)
    await user.type(field, ' ab ')

    const submit = screen.getByRole('button', { name: 'Отклонить' })
    expect(submit).toBeDisabled()

    await user.clear(field)
    await user.type(field, '  нет документов  ')
    expect(submit).not.toBeDisabled()

    await user.click(submit)
    expect(m.reject).toHaveBeenCalledWith(
      { uaId: 11, comment: 'нет документов' }, expect.anything(),
    )
  })

  it('отвязка спрашивает подтверждение и показывает адрес', async () => {
    const user = userEvent.setup()
    render(<ResidentApartmentsList residentId={1} apartments={[binding()]} />)

    await user.click(screen.getByRole('button', { name: 'Отвязать' }))

    // Адрес есть и в самой строке привязки — ищем именно внутри диалога,
    // иначе тест зелёный даже когда диалог не показывает, ЧТО отвязывают.
    const dialog = screen.getByRole('alertdialog')
    expect(within(dialog).getByText(/Двор-7 · ул. Тестовая 1 · кв. 42/)).toBeInTheDocument()
    expect(m.remove).not.toHaveBeenCalled()
  })

  it('переключение роли шлёт инвертированное значение', async () => {
    const user = userEvent.setup()
    render(<ResidentApartmentsList residentId={1} apartments={[binding({ is_owner: true })]} />)

    await user.click(screen.getByRole('button', { name: 'Отметить жильцом' }))
    expect(m.update).toHaveBeenCalledWith({ uaId: 11, is_owner: false })
  })

  it('rejected-привязка редактированию не подлежит, но отвязать её можно', () => {
    render(<ResidentApartmentsList residentId={1}
                                   apartments={[binding({ status: 'rejected', is_primary: false })]} />)
    expect(screen.queryByRole('button', { name: 'Подтвердить' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Отметить владельцем' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Отвязать' })).toBeInTheDocument()
  })
})
