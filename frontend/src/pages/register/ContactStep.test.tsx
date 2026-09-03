import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../../test/test-utils'
import { ContactStep } from './ContactStep'

// Спека §5.1 contact: телефон только через Telegram.WebApp.requestContact;
// контакт приходит боту, TWA опрашивает contact-status до появления номера.

const { sdk } = vi.hoisted(() => ({
  sdk: { tg: null as null | { requestContact?: (cb: (sent: boolean) => void) => void } },
}))
vi.mock('../../twa/hooks/useTelegramSDK', () => ({
  useTelegramSDK: () => ({ tg: sdk.tg, haptic: () => {} }),
}))

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})
afterEach(() => {
  vi.useRealTimers()
})

describe('ContactStep', () => {
  it('без requestContact в SDK просит обновить Telegram, кнопки нет', () => {
    sdk.tg = {}
    render(<ContactStep ticket="t" contactStatus={vi.fn()} onDone={vi.fn()} />)
    expect(screen.getByText('Обновите Telegram, чтобы поделиться контактом.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Поделиться контактом' })).toBeNull()
  })

  it('отказ в попапе → подсказка, кнопка остаётся', async () => {
    sdk.tg = { requestContact: (cb) => cb(false) }
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<ContactStep ticket="t" contactStatus={vi.fn()} onDone={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Поделиться контактом' }))
    expect(await screen.findByText('Без номера телефона регистрация невозможна.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Поделиться контактом' })).toBeInTheDocument()
  })

  it('после отправки опрашивает contact-status и зовёт onDone с телефоном', async () => {
    sdk.tg = { requestContact: (cb) => cb(true) }
    const contactStatus = vi
      .fn()
      .mockResolvedValueOnce({ phone: null })
      .mockResolvedValueOnce({ phone: '+998901234567' })
    const onDone = vi.fn()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<ContactStep ticket="t" contactStatus={contactStatus} onDone={onDone} />)
    await user.click(screen.getByRole('button', { name: 'Поделиться контактом' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(1600) })
    await act(async () => { await vi.advanceTimersByTimeAsync(1600) })
    expect(onDone).toHaveBeenCalledWith('+998901234567')
    expect(contactStatus).toHaveBeenCalledWith('t')
  })

  it('30 секунд без телефона → таймаут и кнопка «Проверить ещё раз»', async () => {
    sdk.tg = { requestContact: (cb) => cb(true) }
    const contactStatus = vi.fn().mockResolvedValue({ phone: null })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<ContactStep ticket="t" contactStatus={contactStatus} onDone={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Поделиться контактом' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(31000) })
    expect(await screen.findByText('Бот ещё не получил ваш контакт.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Проверить ещё раз' })).toBeInTheDocument()
  })
})
