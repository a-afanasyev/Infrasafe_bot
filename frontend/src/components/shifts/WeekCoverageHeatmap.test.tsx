import { describe, expect, it } from 'vitest'
import { render, screen } from '../../test/test-utils'
import WeekCoverageHeatmap from './WeekCoverageHeatmap'
import type { ShiftBrief } from '../../hooks/useShifts'

/**
 * Тепловая карта недели (решение владельца 2026-08-27): у дня и месяца
 * карты покрытия были, у недели — нет. 7 строк-дней × 24 часа, семантика
 * ячейки — «сколько исполнителей на смене в этот час» (как в дневной).
 */

function makeShift(overrides: Partial<ShiftBrief> = {}): ShiftBrief {
  return {
    id: 1,
    user_id: 10,
    executor_name: 'Иван Тестов',
    status: 'active',
    shift_type: 'day',
    start_time: '2026-06-08T10:00:00+05:00',
    end_time: '2026-06-08T12:00:00+05:00',
    max_requests: 5,
    current_request_count: 0,
    load_percentage: 0,
    specialization_focus: ['electrician'],
    ...overrides,
  }
}

// Среда 10.06.2026 → неделя Пн 08.06 – Вс 14.06.
const weekAnchor = new Date('2026-06-10T12:00:00+05:00')

function cell(day: number, hour: number): HTMLElement {
  return screen.getByTestId(`wk-cell-${day}-${hour}`)
}

describe('WeekCoverageHeatmap', () => {
  it('считает исполнителей в часовой ячейке; конец 12:00 в час 12 не попадает', () => {
    render(
      <WeekCoverageHeatmap
        shifts={[makeShift({ id: 1, user_id: 10 }), makeShift({ id: 2, user_id: 20 })]}
        weekAnchor={weekAnchor}
      />,
    )
    expect(cell(0, 10)).toHaveTextContent('2')
    expect(cell(0, 11)).toHaveTextContent('2')
    expect(cell(0, 12)).toHaveTextContent('0')
    expect(cell(0, 9)).toHaveTextContent('0')
  })

  it('ночная смена ложится в оба дня', () => {
    render(
      <WeekCoverageHeatmap
        shifts={[makeShift({
          start_time: '2026-06-08T20:00:00+05:00',
          end_time: '2026-06-09T08:00:00+05:00',
        })]}
        weekAnchor={weekAnchor}
      />,
    )
    expect(cell(0, 20)).toHaveTextContent('1')
    expect(cell(0, 23)).toHaveTextContent('1')
    expect(cell(1, 0)).toHaveTextContent('1')
    expect(cell(1, 7)).toHaveTextContent('1')
    expect(cell(1, 8)).toHaveTextContent('0')
  })

  it('смена вне недели не учитывается; 7 строк-дней на месте', () => {
    render(
      <WeekCoverageHeatmap
        shifts={[makeShift({
          start_time: '2026-06-01T10:00:00+05:00',
          end_time: '2026-06-01T12:00:00+05:00',
        })]}
        weekAnchor={weekAnchor}
      />,
    )
    expect(cell(0, 10)).toHaveTextContent('0')
    // 7 дней недели, Пн..Вс.
    expect(screen.getAllByTestId(/^wk-day-label-/)).toHaveLength(7)
  })
})
