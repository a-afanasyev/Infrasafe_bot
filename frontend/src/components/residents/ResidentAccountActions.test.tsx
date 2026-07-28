import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../../test/test-utils'
import ResidentAccountActions from './ResidentAccountActions'
import type { ResidentProfile } from '../../types/api'

const { approveMutate, blockMutate, unblockMutate } = vi.hoisted(() => ({
  approveMutate: vi.fn(),
  blockMutate: vi.fn(),
  unblockMutate: vi.fn(),
}))

vi.mock('../../hooks/useResidents', () => ({
  useApproveResident: () => ({ mutate: approveMutate, isPending: false }),
  useBlockResident: () => ({ mutate: blockMutate, isPending: false }),
  useUnblockResident: () => ({ mutate: unblockMutate, isPending: false }),
}))

function profile(over: Partial<ResidentProfile> = {}): ResidentProfile {
  return {
    id: 1, telegram_id: 5001, username: null,
    first_name: 'Иван', last_name: 'Иванов', phone: null,
    status: 'pending', verification_status: 'pending',
    verification_notes: null, verification_date: null,
    language: 'ru', created_at: null,
    roles: ['applicant'], apartments: [], documents: [],
    latest_verification: null,
    ...over,
  }
}

beforeEach(() => {
  approveMutate.mockClear()
  blockMutate.mockClear()
  unblockMutate.mockClear()
})

describe('ResidentAccountActions', () => {
  it('одобрение доступно только для ожидающего аккаунта', () => {
    render(<ResidentAccountActions resident={profile({ status: 'pending' })} />)
    expect(screen.getByRole('button', { name: 'Одобрить аккаунт' })).toBeInTheDocument()
  })

  it('одобренному аккаунту кнопка одобрения не показывается', () => {
    render(<ResidentAccountActions resident={profile({ status: 'approved' })} />)
    expect(screen.queryByRole('button', { name: 'Одобрить аккаунт' })).not.toBeInTheDocument()
  })

  it('блокировка СКРЫТА у мультиролевого и объяснена текстом', () => {
    // users.status общий на все роли: блокировка жителя-исполнителя отняла бы
    // рабочий доступ, поэтому бэкенд отвечает 409. Показывать кнопку, которая
    // гарантированно упадёт, — худший вариант, чем не показывать вовсе.
    render(<ResidentAccountActions
      resident={profile({ status: 'approved', roles: ['applicant', 'executor'] })} />)

    expect(screen.queryByRole('button', { name: 'Заблокировать' })).not.toBeInTheDocument()
    expect(screen.getByText(/роли персонала/)).toBeInTheDocument()
    expect(screen.getByText(/executor/)).toBeInTheDocument()
  })

  it('капабилити контролёра показаний блокировке не мешает', () => {
    render(<ResidentAccountActions
      resident={profile({ status: 'approved', roles: ['applicant', 'resource_meter_entry'] })} />)
    expect(screen.getByRole('button', { name: 'Заблокировать' })).toBeInTheDocument()
  })

  it('разблокировка показывается только заблокированному', () => {
    render(<ResidentAccountActions resident={profile({ status: 'blocked' })} />)
    expect(screen.getByRole('button', { name: 'Разблокировать' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Заблокировать' })).not.toBeInTheDocument()
  })

  it('блокировка требует причину от 3 символов', async () => {
    const user = userEvent.setup()
    render(<ResidentAccountActions resident={profile({ status: 'approved' })} />)

    await user.click(screen.getByRole('button', { name: 'Заблокировать' }))
    const field = screen.getByPlaceholderText(/Причина блокировки/)
    await user.type(field, 'ab')

    const submit = screen.getByRole('button', { name: 'Подтвердить блокировку' })
    expect(submit).toBeDisabled()

    await user.type(field, 'c')
    expect(submit).not.toBeDisabled()

    await user.click(submit)
    expect(blockMutate).toHaveBeenCalledWith({ reason: 'abc' }, expect.anything())
  })
})
