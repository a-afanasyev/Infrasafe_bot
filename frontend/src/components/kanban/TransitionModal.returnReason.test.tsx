import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/react'
import { render } from '../../test/test-utils'
import TransitionModal from './TransitionModal'

// Волна C: причина возврата стала обязательной в ядре, поэтому drag
// «Исполнено»→«В работе» без неё теперь отдаёт 422. Модалка обязана собрать
// причину — и только для возврата, не для resume из «Закуп»/«Уточнение».

describe('TransitionModal — возврат в работу с причиной', () => {
  it('для возврата показывает поле причины, а не выбор исполнителя', () => {
    render(
      <TransitionModal
        requestNumber="260817-001"
        targetStatus="В работе"
        sourceStatus="Исполнено"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    )

    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.queryAllByText(/дежурн/i)).toHaveLength(0)
  })

  it('кнопка подтверждения заблокирована, пока причина пуста', async () => {
    render(
      <TransitionModal
        requestNumber="260817-001"
        targetStatus="В работе"
        sourceStatus="Выполнена"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    )

    const confirm = screen.getByRole('button', { name: /подтвердить|сохранить|ок/i })
    expect(confirm).toBeDisabled()

    await userEvent.type(screen.getByRole('textbox'), 'Переделать шов')

    expect(confirm).toBeEnabled()
  })

  it('шлёт причину в поле return_reason', async () => {
    // Имя поля транспортное: сервер переводит его в payload `reason`
    // для MANAGER_RETURN_TO_WORK.
    const onConfirm = vi.fn()
    render(
      <TransitionModal
        requestNumber="260817-001"
        targetStatus="В работе"
        sourceStatus="Возвращена"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    )

    await userEvent.type(screen.getByRole('textbox'), '  Переделать шов  ')
    await userEvent.click(screen.getByRole('button', { name: /подтвердить|сохранить|ок/i }))

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'В работе', return_reason: 'Переделать шов' }),
    )
    expect(onConfirm.mock.calls[0][0]).not.toHaveProperty('executor_id')
  })

  it('для взятия из «Новая» причину не спрашивает', () => {
    render(
      <TransitionModal
        requestNumber="260817-001"
        targetStatus="В работе"
        sourceStatus="Новая"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    )

    expect(screen.getAllByText(/дежурн/i).length).toBeGreaterThan(0)
  })
})
