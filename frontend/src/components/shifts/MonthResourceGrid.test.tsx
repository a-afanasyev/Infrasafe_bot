import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '../../test/test-utils'
import MonthResourceGrid from './MonthResourceGrid'
import SpecializationFilterBar from './SpecializationFilterBar'
import type { ShiftBrief } from '../../hooks/useShifts'

/**
 * Доработки расписания смен (решение владельца 2026-08-27):
 * итог смен/часов — рядом с ФИО (Σ-колонка справа снята), колонка ФИО
 * растягивается ручкой, сайдбар специализаций — локализованный.
 */

function makeShift(overrides: Partial<ShiftBrief> = {}): ShiftBrief {
  return {
    id: 1,
    user_id: 10,
    executor_name: 'Иван Тестов',
    status: 'active',
    shift_type: 'day',
    start_time: '2026-06-10T09:00:00+05:00',
    end_time: '2026-06-10T17:00:00+05:00',
    max_requests: 5,
    current_request_count: 0,
    load_percentage: 0,
    specialization_focus: ['electrician'],
    ...overrides,
  }
}

const monthAnchor = new Date('2026-06-15T12:00:00+05:00')

describe('MonthResourceGrid', () => {
  it('итог смен и часов стоит рядом с ФИО, отдельной Σ-колонки нет', () => {
    render(
      <MonthResourceGrid
        shifts={[makeShift({ id: 1 }), makeShift({ id: 2, start_time: '2026-06-11T09:00:00+05:00', end_time: '2026-06-11T17:00:00+05:00' })]}
        monthAnchor={monthAnchor}
        selectedSpec={null}
        onShiftClick={vi.fn()}
      />,
    )
    expect(screen.getByText('Иван Тестов')).toBeInTheDocument()
    // 2 смены × 8 ч — бейдж в строке исполнителя.
    expect(screen.getByText(/2\s*·\s*16ч/)).toBeInTheDocument()
    // Σ-заголовка больше нет.
    expect(screen.queryByText('Σ')).not.toBeInTheDocument()
  })

  it('колонка ФИО имеет ручку ресайза', () => {
    render(
      <MonthResourceGrid
        shifts={[makeShift()]}
        monthAnchor={monthAnchor}
        selectedSpec={null}
        onShiftClick={vi.fn()}
      />,
    )
    expect(screen.getByRole('separator')).toBeInTheDocument()
  })
})

describe('SpecializationFilterBar локализация', () => {
  it('канон-ключ специализации показывается по-русски, «Все» и «Универсалы» на месте', () => {
    render(
      <SpecializationFilterBar
        shifts={[makeShift(), makeShift({ id: 3, specialization_focus: [] })]}
        selectedSpec={null}
        onSelectSpec={vi.fn()}
      />,
    )
    // electrician → «Электрика», сырого ключа в UI нет.
    expect(screen.getByText('Электрика')).toBeInTheDocument()
    expect(screen.queryByText('electrician')).not.toBeInTheDocument()
    expect(screen.getByText('Универсалы')).toBeInTheDocument()
  })
})
