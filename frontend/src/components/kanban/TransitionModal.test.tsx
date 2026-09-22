import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import TransitionModal from './TransitionModal'
import { MAX_REQUEST_TEXT_LENGTH } from '../../constants'

function noop() {}

// FEAT-группы (followup #2): «Назначить дежурному» должно назначать на ГРУППУ-
// специализацию (сервер резолвит спец по категории), а не делать status-only
// переход без исполнителя. Фронт сигналит это флагом assign_to_duty.
describe('TransitionModal — назначение дежурному (followup #2)', () => {
  it('шлёт assign_to_duty:true при выборе «Дежурный» для «В работе»', async () => {
    server.use(http.get('*/api/v2/shifts/employees', () => HttpResponse.json([])))
    const onConfirm = vi.fn()
    render(
      <TransitionModal
        requestNumber="260101-001"
        targetStatus="В работе"
        onConfirm={onConfirm}
        onCancel={noop}
      />,
    )
    await userEvent.click(await screen.findByRole('button', { name: /Дежурный/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Подтвердить' }))
    expect(onConfirm).toHaveBeenCalledWith({ status: 'В работе', assign_to_duty: true })
  })

  it('конкретный исполнитель шлёт executor_id, без assign_to_duty', async () => {
    server.use(http.get('*/api/v2/shifts/employees', () =>
      HttpResponse.json([{ id: 7, first_name: 'Сантехник', last_name: 'Тест' }])))
    const onConfirm = vi.fn()
    render(
      <TransitionModal
        requestNumber="260101-001"
        targetStatus="В работе"
        onConfirm={onConfirm}
        onCancel={noop}
      />,
    )
    await userEvent.click(await screen.findByRole('button', { name: /Сантехник Тест/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Подтвердить' }))
    expect(onConfirm).toHaveBeenCalledWith({ status: 'В работе', executor_id: 7 })
  })
})

// Сек-ревью A9: API режет текстовые поля PATCH на MAX_DESCRIPTION_LENGTH (2000)
// и отвечает 422 — поле ввода не даёт набрать больше.
describe('TransitionModal — лимит длины текста', () => {
  it.each(['Закуп', 'Уточнение', 'Выполнена'])('textarea «%s» ограничена MAX_REQUEST_TEXT_LENGTH', (status) => {
    render(
      <TransitionModal requestNumber="260101-001" targetStatus={status} onConfirm={noop} onCancel={noop} />,
    )
    expect(screen.getByRole('textbox')).toHaveAttribute('maxLength', String(MAX_REQUEST_TEXT_LENGTH))
  })
})
