import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../test/test-utils'
import RegisterPage from './RegisterPage'

// Спека 2026-09-03 §5.1: шаги contact → address → confirm → pending.
// useRegistration мокаем целиком; ContactStep и AddressCascade — заглушки,
// у них свои тесты.
const { mockReg } = vi.hoisted(() => ({
  mockReg: {
    initData: '' as string,
    start: vi.fn(), submit: vi.fn(),
    yards: vi.fn(), buildings: vi.fn(), apartments: vi.fn(), contactStatus: vi.fn(),
  },
}))
vi.mock('../hooks/useRegistration', () => ({ useRegistration: () => mockReg }))
vi.mock('./register/ContactStep', () => ({
  ContactStep: ({ onDone }: { onDone: (p: string) => void }) => (
    <button onClick={() => onDone('+998900000001')}>stub-contact</button>
  ),
}))
vi.mock('./register/AddressCascade', () => ({
  AddressCascade: ({ onSelect }: { onSelect: (a: unknown, l: unknown) => void }) => (
    <button onClick={() => onSelect({ id: 7, apartment_number: '5' }, { yard: 'Двор-Y', building: 'Дом 1' })}>
      stub-address
    </button>
  ),
}))

const START = {
  registration_ticket: 'ticket-1',
  prefill: { first_name: 'Иван', last_name: 'П', phone: '+998901112233' },
}

beforeEach(() => {
  mockReg.initData = 'tg-init-data'
  mockReg.start.mockReset()
  mockReg.submit.mockReset()
})

describe('RegisterPage', () => {
  it('с телефоном в prefill сразу шаг адреса, затем confirm с данными', async () => {
    mockReg.start.mockResolvedValue(START)
    const user = userEvent.setup()
    render(<RegisterPage />)
    await user.click(await screen.findByText('stub-address'))
    expect(await screen.findByLabelText('ФИО')).toHaveValue('Иван П')
    expect(screen.getByText('+998901112233')).toBeInTheDocument()
    expect(screen.getByText('Двор-Y · Дом 1 · кв 5')).toBeInTheDocument()
    expect(screen.queryByText('stub-contact')).toBeNull()
  })

  it('без телефона — сначала шаг контакта', async () => {
    mockReg.start.mockResolvedValue({ ...START, prefill: { first_name: 'Иван' } })
    const user = userEvent.setup()
    render(<RegisterPage />)
    await user.click(await screen.findByText('stub-contact'))
    expect(await screen.findByText('stub-address')).toBeInTheDocument()
  })

  it('«Изменить адрес» возвращает к каскаду', async () => {
    mockReg.start.mockResolvedValue(START)
    const user = userEvent.setup()
    render(<RegisterPage />)
    await user.click(await screen.findByText('stub-address'))
    await user.click(await screen.findByRole('button', { name: 'Изменить адрес' }))
    expect(await screen.findByText('stub-address')).toBeInTheDocument()
  })

  it('submit шлёт full_name и apartment_id, затем pending', async () => {
    mockReg.start.mockResolvedValue(START)
    mockReg.submit.mockResolvedValue({ status: 'pending' })
    const user = userEvent.setup()
    render(<RegisterPage />)
    await user.click(await screen.findByText('stub-address'))
    await user.click(await screen.findByRole('button', { name: 'Отправить заявку' }))
    expect(await screen.findByText('Заявка отправлена')).toBeInTheDocument()
    expect(mockReg.submit).toHaveBeenCalledWith('ticket-1', { full_name: 'Иван П', apartment_id: 7 })
  })

  it('409 «уже зарегистрирован» на start → экран already_registered', async () => {
    mockReg.start.mockRejectedValue({ response: { status: 409, data: { detail: 'already approved' } } })
    render(<RegisterPage />)
    expect(await screen.findByText('Вы уже зарегистрированы. Перейдите в приложение.')).toBeInTheDocument()
  })

  it('без initData — просьба открыть из Telegram', async () => {
    mockReg.initData = ''
    render(<RegisterPage />)
    expect(await screen.findByText('Откройте эту страницу из Telegram, чтобы зарегистрироваться.', {}, { timeout: 3000 })).toBeInTheDocument()
  })
})
