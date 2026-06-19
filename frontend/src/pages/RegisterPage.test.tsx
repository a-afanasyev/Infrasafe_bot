import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../test/test-utils'
import RegisterPage from './RegisterPage'

// TEST-068 Phase 5: страница самостоятельной регистрации жителя. Управляется
// хуком useRegistration (initData из Telegram SDK + start/submit) — мокаем его,
// чтобы прогнать фазовые переходы form / pending / already_registered.

const { mockReg } = vi.hoisted(() => ({
  mockReg: { initData: '' as string, start: vi.fn(), submit: vi.fn() },
}))

vi.mock('../hooks/useRegistration', () => ({
  useRegistration: () => mockReg,
}))

const START_OK = {
  registration_ticket: 'ticket-1',
  apartments: [{ id: 1, yard_name: 'Двор-Y', building_address: 'Дом 1', apartment_number: '5' }],
  prefill: { first_name: 'Иван', last_name: 'П', phone: '+998901112233' },
}

beforeEach(() => {
  mockReg.initData = 'tg-init-data'
  mockReg.start.mockReset()
  mockReg.submit.mockReset()
})

describe('RegisterPage', () => {
  it('renders the form prefilled after start() resolves', async () => {
    mockReg.start.mockResolvedValue(START_OK)
    render(<RegisterPage />)
    const name = await screen.findByLabelText('ФИО')
    expect(name).toHaveValue('Иван П')
    expect(screen.getByLabelText('Телефон')).toHaveValue('+998901112233')
    expect(screen.getByText('Двор-Y · Дом 1 · кв 5')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Отправить заявку' })).toBeInTheDocument()
  })

  it('shows the pending screen after a successful submit', async () => {
    mockReg.start.mockResolvedValue(START_OK)
    mockReg.submit.mockResolvedValue({ status: 'pending' })
    const user = userEvent.setup()
    render(<RegisterPage />)
    await screen.findByLabelText('ФИО')
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))
    expect(await screen.findByText('Заявка отправлена')).toBeInTheDocument()
    expect(mockReg.submit).toHaveBeenCalledWith('ticket-1', expect.objectContaining({ apartment_id: 1 }))
  })

  it('shows already-registered when start() returns 409 approved', async () => {
    mockReg.start.mockRejectedValue({ response: { status: 409, data: { detail: 'already approved' } } })
    render(<RegisterPage />)
    expect(await screen.findByText('Вы уже зарегистрированы. Перейдите в приложение.')).toBeInTheDocument()
  })
})
