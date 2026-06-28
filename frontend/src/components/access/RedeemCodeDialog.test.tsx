import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import RedeemCodeDialog from './RedeemCodeDialog'

/**
 * Диалог проверки одноразового гостевого кода оператором (§9.3):
 *  - успех 200 → раскрытие квартиры + «шлагбаум открыт»;
 *  - 422 code_invalid → общий текст (деталь не раскрываем);
 *  - 429 too_many_attempts → текст блокировки.
 */

const REDEEM = '*/api/v1/access/passes/redeem-code'

async function typeCodeAndCheck() {
  const input = screen.getByRole('textbox')
  await userEvent.type(input, '12345678')
  await userEvent.click(screen.getByRole('button', { name: 'Проверить' }))
}

describe('RedeemCodeDialog — проверка кода гостя', () => {
  beforeEach(() => server.resetHandlers())

  it('успех: раскрывает квартиру, тип пропуска и факт открытия шлагбаума', async () => {
    server.use(
      http.post(REDEEM, () =>
        HttpResponse.json({
          apartment_id: 12,
          pass_type: 'guest',
          valid_until: '2026-07-01T12:00:00Z',
          command: { command_id: 'cmd-abc', barrier_id: 3 },
        }),
      ),
    )

    render(<RedeemCodeDialog open onClose={() => {}} />)
    await typeCodeAndCheck()

    expect(await screen.findByText('Шлагбаум открыт')).toBeInTheDocument()
    // Квартира раскрыта.
    expect(screen.getByText('12')).toBeInTheDocument()
    // Тип пропуска (guest → «Гостевой»).
    expect(screen.getByText('Гостевой')).toBeInTheDocument()
    // command_id показан.
    expect(screen.getByText('cmd-abc')).toBeInTheDocument()
  })

  it('422: общая ошибка без раскрытия деталей', async () => {
    server.use(
      http.post(REDEEM, () => HttpResponse.json({ error: 'code_invalid' }, { status: 422 })),
    )

    render(<RedeemCodeDialog open onClose={() => {}} />)
    await typeCodeAndCheck()

    expect(await screen.findByText('Код неверный или недействителен')).toBeInTheDocument()
    // Квартира НЕ раскрыта.
    expect(screen.queryByTestId('redeem-result')).not.toBeInTheDocument()
  })

  it('429: текст блокировки по числу попыток', async () => {
    server.use(
      http.post(REDEEM, () => HttpResponse.json({ error: 'too_many_attempts' }, { status: 429 })),
    )

    render(<RedeemCodeDialog open onClose={() => {}} />)
    await typeCodeAndCheck()

    expect(await screen.findByText('Слишком много попыток, попробуйте позже')).toBeInTheDocument()
  })
})
