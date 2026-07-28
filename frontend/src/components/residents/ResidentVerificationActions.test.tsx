import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../../test/test-utils'
import ResidentVerificationActions from './ResidentVerificationActions'
import type { ResidentProfile } from '../../types/api'

const m = vi.hoisted(() => ({ request: vi.fn(), approve: vi.fn(), reject: vi.fn() }))

vi.mock('../../hooks/useResidents', () => ({
  useRequestDocuments: () => ({ mutate: m.request, isPending: false }),
  useApproveVerification: () => ({ mutate: m.approve, isPending: false }),
  useRejectVerification: () => ({ mutate: m.reject, isPending: false }),
}))

function profile(over: Partial<ResidentProfile> = {}): ResidentProfile {
  return {
    id: 1, telegram_id: 5001, username: null,
    first_name: 'Иван', last_name: 'Иванов', phone: null,
    status: 'approved', verification_status: 'requested',
    verification_notes: null, verification_date: null,
    language: 'ru', created_at: null,
    roles: ['applicant'], apartments: [], documents: [],
    latest_verification: null,
    ...over,
  }
}

beforeEach(() => {
  m.request.mockClear(); m.approve.mockClear(); m.reject.mockClear()
})

describe('ResidentVerificationActions', () => {
  it('решение доступно, пока ось верификации открыта', () => {
    render(<ResidentVerificationActions resident={profile({ verification_status: 'pending' })} />)
    expect(screen.getByRole('button', { name: 'Верифицировать' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Отклонить верификацию' })).toBeInTheDocument()
  })

  it('у закрытой оси решение скрыто, а запрос документов остаётся', () => {
    // Бэкенд отвечает 409 на уже закрытую верификацию — кнопке, которая
    // гарантированно упадёт, тут не место. Запрос документов при этом
    // разрешён из любого состояния: паспорт меняют.
    render(<ResidentVerificationActions resident={profile({ verification_status: 'verified' })} />)
    expect(screen.queryByRole('button', { name: 'Верифицировать' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Запросить документы' })).toBeInTheDocument()
  })

  it('запрос требует и тип документа, и комментарий', async () => {
    const user = userEvent.setup()
    render(<ResidentVerificationActions resident={profile()} />)

    await user.click(screen.getByRole('button', { name: 'Запросить документы' }))
    const submit = screen.getByRole('button', { name: 'Запросить' })
    expect(submit).toBeDisabled()

    await user.click(screen.getByLabelText('Паспорт'))
    expect(submit).toBeDisabled()          // тип есть, комментария нет

    await user.type(screen.getByPlaceholderText(/Что именно нужно/), 'нужен паспорт')
    expect(submit).not.toBeDisabled()

    await user.click(submit)
    expect(m.request).toHaveBeenCalledWith(
      { document_types: ['passport'], comment: 'нужен паспорт' }, expect.anything(),
    )
  })

  it('подтверждение честно предупреждает о последствиях', async () => {
    const user = userEvent.setup()
    render(<ResidentVerificationActions resident={profile()} />)

    await user.click(screen.getByRole('button', { name: 'Верифицировать' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent(/квартиры на модерации будут одобрены/i)
    // Формулировка про копии обязана остаться: очистка Media Service
    // best-effort, и обещать полное стирание было бы враньём.
    expect(dialog).toHaveTextContent(/копии файлов могут сохраниться/i)
  })

  it('отказ требует причину от 3 символов', async () => {
    const user = userEvent.setup()
    render(<ResidentVerificationActions resident={profile()} />)

    await user.click(screen.getByRole('button', { name: 'Отклонить верификацию' }))
    const field = screen.getByPlaceholderText(/Причина отказа/)
    await user.type(field, 'ab')

    const submit = screen.getAllByRole('button', { name: 'Отклонить верификацию' }).at(-1)!
    expect(submit).toBeDisabled()

    await user.type(field, 'c')
    expect(submit).not.toBeDisabled()
    await user.click(submit)
    expect(m.reject).toHaveBeenCalledWith({ notes: 'abc' }, expect.anything())
  })
})
