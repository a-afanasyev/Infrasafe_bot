import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { apiClient } from '../../api/client'
import ReassignExecutorModal from './ReassignExecutorModal'

/**
 * Смена исполнителя из карточки заявки.
 *
 * Шпионим по `apiClient.patch`, а не по msw-хендлеру: нам важно ЧТО именно
 * уходит на сервер (тело определяет, какое каноническое действие выполнится),
 * а не только факт запроса.
 */

const EMPLOYEES = [
  { id: 5, first_name: 'Иван', last_name: 'Иванов', phone: null,
    specialization: ['plumber'], active_shift_id: 11,
    verification_status: 'verified', status: 'approved', roles: ['executor'] },
  { id: 7, first_name: 'Пётр', last_name: 'Петров', phone: null,
    specialization: ['plumber'], active_shift_id: null,
    verification_status: 'verified', status: 'approved', roles: ['executor'] },
]

function mockEmployees(list = EMPLOYEES) {
  server.use(http.get('*/api/v2/shifts/employees', () => HttpResponse.json(list)))
}

function noop() {}

beforeEach(() => {
  vi.restoreAllMocks()
})

async function renderModal(over: Record<string, unknown> = {}) {
  mockEmployees()
  render(
    <ReassignExecutorModal
      requestNumber="260101-001"
      currentExecutorId={5}
      currentExecutorName="Иван Иванов"
      onClose={noop}
      {...over}
    />
  )
  await screen.findByText('Пётр Петров')
}

describe('ReassignExecutorModal', () => {
  it('исключает текущего исполнителя из списка', async () => {
    await renderModal()

    expect(screen.getByText('Пётр Петров')).toBeInTheDocument()
    // Иван — текущий; предлагать его значит предлагать «оставить как есть»,
    // что сервер отклонит как повтор.
    expect(screen.queryByText('Иван Иванов')).not.toBeInTheDocument()
  })

  it('показывает, кто на смене', async () => {
    mockEmployees([
      { ...EMPLOYEES[1], active_shift_id: 99 },
    ])
    render(
      <ReassignExecutorModal requestNumber="260101-001" currentExecutorId={5}
        currentExecutorName="Иван" onClose={noop} />
    )
    expect(await screen.findByText(/На смене/)).toBeInTheDocument()
  })

  it('шлёт executor_id БЕЗ status — это канон MANAGER_ASSIGN', async () => {
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ data: {} } as never)
    await renderModal()

    await userEvent.click(screen.getByText('Пётр Петров'))
    await userEvent.click(screen.getByRole('button', { name: 'Переназначить' }))

    await waitFor(() => expect(patch).toHaveBeenCalled())
    const [url, body] = patch.mock.calls[0]
    expect(url).toBe('/api/v2/requests/260101-001')
    // status в теле превратил бы это в статусный переход, а не в назначение.
    expect(body).toEqual({ executor_id: 7 })
  })

  it('«дежурному» уходит как assign_to_duty со статусом', async () => {
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ data: {} } as never)
    await renderModal()

    await userEvent.click(screen.getByText('Дежурный'))
    await userEvent.click(screen.getByRole('button', { name: 'Переназначить' }))

    await waitFor(() => expect(patch).toHaveBeenCalled())
    expect(patch.mock.calls[0][1]).toEqual({ status: 'В работе', assign_to_duty: true })
  })

  it('кнопка подтверждения заблокирована, пока никто не выбран', async () => {
    await renderModal()
    expect(screen.getByRole('button', { name: 'Переназначить' })).toBeDisabled()
  })

  it('без текущего исполнителя это НАЗНАЧЕНИЕ, а не переназначение', async () => {
    mockEmployees()
    render(
      <ReassignExecutorModal requestNumber="260101-001" currentExecutorId={null}
        currentExecutorName={null} onClose={noop} />
    )
    await screen.findByText('Пётр Петров')

    expect(screen.getByRole('button', { name: 'Назначить' })).toBeInTheDocument()
    // Исключать некого — оба кандидата на месте.
    expect(screen.getByText('Иван Иванов')).toBeInTheDocument()
  })

  it('показывает причину отказа 409, а не общую ошибку', async () => {
    // «Нет дежурного» — осмысленный ответ сервера; подменять его на
    // «не удалось сохранить» значит скрыть от менеджера, что делать дальше.
    const detail = 'Нет дежурного исполнителя со специализацией plumber на смене прямо сейчас.'
    vi.spyOn(apiClient, 'patch').mockRejectedValue(
      Object.assign(new Error('409'), {
        isAxiosError: true,
        name: 'AxiosError',
        response: { status: 409, data: { detail } },
      })
    )
    await renderModal()

    await userEvent.click(screen.getByText('Дежурный'))
    await userEvent.click(screen.getByRole('button', { name: 'Переназначить' }))

    expect(await screen.findByText(detail)).toBeInTheDocument()
  })

  it('объясняет пустой список, а не показывает пустоту', async () => {
    // Единственный подходящий — текущий исполнитель: список пуст ВСЕГДА.
    mockEmployees([EMPLOYEES[0]])
    render(
      <ReassignExecutorModal requestNumber="260101-001" currentExecutorId={5}
        currentExecutorName="Иван" onClose={noop} />
    )
    expect(await screen.findByText(/Других подходящих исполнителей нет/)).toBeInTheDocument()
  })
})
