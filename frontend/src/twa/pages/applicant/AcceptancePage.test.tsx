import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../../test/test-utils'
import AcceptancePage from './AcceptancePage'

// Регрессия прод-бага 2026-07-25: кнопка «Вернуть» отправляла
// status: 'В работе' — ребро, снятое у заявителя (это MANAGER_RETURN_TO_WORK),
// и падала с «no action maps 'Исполнено' -> 'В работе' for this actor».
// Канон-ребро — APPLICANT_RETURN: «Исполнено» → «Возвращена» + обязательный
// return_reason.
const { mockGet, mockPatch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPatch: vi.fn(),
}))

vi.mock('../../twaClient', () => ({
  twaClient: { get: mockGet, patch: mockPatch },
}))

const REQUEST = {
  request_number: '260725-011',
  status: 'Исполнено',
  category: 'electricity',
  description: 'Когда включите фонари',
}

beforeEach(() => {
  mockGet.mockReset()
  mockPatch.mockReset()
  mockGet.mockResolvedValue({ data: [REQUEST] })
  mockPatch.mockResolvedValue({ data: {} })
})

async function openCard() {
  render(<AcceptancePage />)
  const card = await screen.findByText('260725-011')
  fireEvent.click(card)
}

describe('AcceptancePage — возврат заявителем', () => {
  it('«Вернуть» неактивна, пока не указана причина', async () => {
    await openCard()

    const returnButton = await screen.findByRole('button', { name: 'Вернуть' })
    expect(returnButton).toBeDisabled()

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'лифт снова встал' } })

    expect(returnButton).toBeEnabled()
  })

  it('отправляет «Возвращена» и причину, а не снятое «В работе»', async () => {
    await openCard()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '  лифт снова встал  ' } })

    fireEvent.click(await screen.findByRole('button', { name: 'Вернуть' }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledTimes(1))
    expect(mockPatch).toHaveBeenCalledWith('/api/v2/requests/260725-011', {
      status: 'Возвращена',
      // Пробелы срезаются: движок принимает любую непустую строку, но в аудит
      // и карточку не должен попадать мусор.
      return_reason: 'лифт снова встал',
    })
  })

  it('пустая причина не уходит на сервер даже пробелами', async () => {
    await openCard()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '   ' } })

    expect(await screen.findByRole('button', { name: 'Вернуть' })).toBeDisabled()
    expect(mockPatch).not.toHaveBeenCalled()
  })

  it('приёмка по-прежнему требует оценку и шлёт «Принято»', async () => {
    // Проверяем, что правка возврата не задела соседнюю кнопку.
    await openCard()

    const acceptButton = await screen.findByRole('button', { name: 'Принять' })
    expect(acceptButton).toBeDisabled()

    // Пятая звезда — последняя из радиогрупп/кнопок рейтинга.
    const stars = screen.getAllByRole('button').filter((b) => b.textContent === '')
    fireEvent.click(stars[stars.length - 1])
    fireEvent.click(await screen.findByRole('button', { name: 'Принять' }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledTimes(1))
    expect(mockPatch.mock.calls[0][1]).toMatchObject({ status: 'Принято' })
  })
})
