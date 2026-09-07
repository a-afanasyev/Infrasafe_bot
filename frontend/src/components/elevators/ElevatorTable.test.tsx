import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { render } from '../../test/test-utils'
import { useTableSort } from '../../hooks/useTableSort'
import type { ElevatorCard } from '../../types/elevators'
import ElevatorTable from './ElevatorTable'
import { ELEVATOR_COLUMNS, ELEVATORS_SORT_STORAGE_KEY } from './elevatorSortColumns'

const ITEM: ElevatorCard = {
  id: 1,
  label: 'ул. Мира, д. 5, подъезд 1, лифт 1',
  building_id: 1,
  building_address: 'ул. Мира, д. 5',
  yard_name: 'Двор',
  entrance_number: 1,
  elevator_number: 1,
  status: 'working',
  status_since: '2026-09-01T10:00:00Z',
  availability_30d: 97,
  open_requests_count: 2,
  is_archived: false,
  flags: { no_contract: false, cert_expired: false, maintenance_overdue: false },
}

/** Обёртка, которая связывает таблицу с настоящим хуком сортировки. */
function Harness() {
  const sort = useTableSort<ElevatorCard>(ELEVATOR_COLUMNS, ELEVATORS_SORT_STORAGE_KEY)
  return (
    <>
      <ElevatorTable items={[ITEM]} sort={sort} />
      <output data-testid="query">{JSON.stringify(sort.queryParams)}</output>
    </>
  )
}

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('ElevatorTable — сортировка', () => {
  it('колонки, которые сервер упорядочить не может, заголовком не кликаются', () => {
    render(<Harness />)
    expect(screen.getByRole('button', { name: 'Лифт' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Доступность 30д' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Флаги' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Действия' })).not.toBeInTheDocument()
  })

  it('клик отправляет колонку и направление в запрос, третий клик их снимает', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const query = () => JSON.parse(screen.getByTestId('query').textContent || '{}')
    const header = () => screen.getByRole('button', { name: 'Статус' })

    expect(query()).toEqual({})
    await user.click(header())
    expect(query()).toEqual({ sort: 'status', order: 'asc' })
    await user.click(header())
    expect(query()).toEqual({ sort: 'status', order: 'desc' })
    await user.click(header())
    expect(query()).toEqual({})
  })

  it('счётчики и даты начинают с убывания — крупное и свежее сверху', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const query = () => JSON.parse(screen.getByTestId('query').textContent || '{}')

    await user.click(screen.getByRole('button', { name: 'Открытых заявок' }))
    expect(query()).toEqual({ sort: 'open_requests', order: 'desc' })
  })

  it('состояние объявлено через aria-sort и переживает перезагрузку страницы', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Статус' }))
    expect(screen.getByRole('columnheader', { name: /Статус/ })).toHaveAttribute('aria-sort', 'ascending')

    unmount()
    render(<Harness />)
    expect(screen.getByRole('columnheader', { name: /Статус/ })).toHaveAttribute('aria-sort', 'ascending')
  })
})
