import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '../../test/test-utils'
import WeekResourceGrid from './WeekResourceGrid'
import type { ShiftBrief } from '../../hooks/useShifts'

// FE-01 regression: useMemo used to sit BELOW the `shifts.length === 0` early
// return, so toggling empty <-> non-empty changed the hook count between
// renders ("Rendered more/fewer hooks than during the previous render").
// These tests re-render across both branches to lock the fix in.

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
    specialization_focus: ['electrics'],
    ...overrides,
  }
}

const weekAnchor = new Date('2026-06-10T12:00:00+05:00')

describe('WeekResourceGrid render-branch switching (FE-01)', () => {
  it('renders empty state without shifts', () => {
    render(<WeekResourceGrid shifts={[]} weekAnchor={weekAnchor} onShiftClick={vi.fn()} />)
    expect(screen.getByText('На этой неделе нет смен')).toBeInTheDocument()
  })

  it('renders executor row with shifts', () => {
    render(
      <WeekResourceGrid shifts={[makeShift()]} weekAnchor={weekAnchor} onShiftClick={vi.fn()} />,
    )
    expect(screen.getByText('Иван Тестов')).toBeInTheDocument()
  })

  it('survives empty -> data -> empty re-renders (hook order stable)', () => {
    const onShiftClick = vi.fn()
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      const { rerender } = render(
        <WeekResourceGrid shifts={[]} weekAnchor={weekAnchor} onShiftClick={onShiftClick} />,
      )
      expect(screen.getByText('На этой неделе нет смен')).toBeInTheDocument()

      rerender(
        <WeekResourceGrid
          shifts={[makeShift()]}
          weekAnchor={weekAnchor}
          onShiftClick={onShiftClick}
        />,
      )
      expect(screen.getByText('Иван Тестов')).toBeInTheDocument()

      rerender(
        <WeekResourceGrid shifts={[]} weekAnchor={weekAnchor} onShiftClick={onShiftClick} />,
      )
      expect(screen.getByText('На этой неделе нет смен')).toBeInTheDocument()

      // React reports hook-order violations via console.error — must be silent.
      const hookErrors = errSpy.mock.calls.filter(args =>
        String(args[0]).toLowerCase().includes('hook'),
      )
      expect(hookErrors).toEqual([])
    } finally {
      errSpy.mockRestore()
    }
  })
})

describe('WeekResourceGrid — читаемые плашки', () => {
  it('короткая смена — полный диапазон, а не обрезок по длительности; ночная — «начало →» и «→ конец»', () => {
    const onShiftClick = vi.fn()
    render(
      <WeekResourceGrid
        shifts={[
          makeShift({ status: 'planned', id: 1, start_time: '2026-06-10T09:00:00+05:00', end_time: '2026-06-10T13:00:00+05:00' }),
          makeShift({ status: 'planned', id: 2, start_time: '2026-06-10T20:00:00+05:00', end_time: '2026-06-11T08:00:00+05:00' }),
        ]}
        weekAnchor={weekAnchor}
        onShiftClick={onShiftClick}
      />,
    )
    expect(screen.getByText('09:00 – 13:00')).toBeInTheDocument()
    expect(screen.getByText('20:00 →')).toBeInTheDocument()
    expect(screen.getByText('→ 08:00')).toBeInTheDocument()
    // Полный диапазон ночной смены — в подсказке обеих её плашек.
    expect(screen.getAllByTitle(/20:00 – 08:00 \+1д/)).toHaveLength(2)
    // Плашка во всю ширину ячейки; позиция в сутках — полоса-подсказка.
    const shortChip = screen.getByText('09:00 – 13:00').closest('button')!
    expect(shortChip.className).toContain('w-full')
    expect(shortChip.style.width).toBe('')
    const hint = shortChip.querySelector('[data-testid="shift-hour-hint"]') as HTMLElement
    expect(hint.style.left).toBe('37.5%')
    expect(hint.style.width).toBe(`${(4 / 24) * 100}%`)
  })

  it('открытая смена — «начало – идёт»; суточная 13:00→13:00 — «13:00 →» и «→ 13:00»', () => {
    render(
      <WeekResourceGrid
        shifts={[
          makeShift({ id: 1, status: 'active', start_time: '2026-06-09T09:00:00+05:00', end_time: null }),
          makeShift({ status: 'planned', id: 2, start_time: '2026-06-10T13:00:00+05:00', end_time: '2026-06-11T13:00:00+05:00' }),
        ]}
        weekAnchor={weekAnchor}
        onShiftClick={vi.fn()}
      />,
    )
    expect(screen.getByText('09:00 – идёт')).toBeInTheDocument()
    expect(screen.getByText('13:00 →')).toBeInTheDocument()
    expect(screen.getByText('→ 13:00')).toBeInTheDocument()
  })

  it('плашки в ячейке идут по времени начала', () => {
    render(
      <WeekResourceGrid
        shifts={[
          makeShift({ status: 'planned', id: 1, start_time: '2026-06-10T14:00:00+05:00', end_time: '2026-06-10T18:00:00+05:00' }),
          makeShift({ status: 'planned', id: 2, start_time: '2026-06-10T09:00:00+05:00', end_time: '2026-06-10T13:00:00+05:00' }),
        ]}
        weekAnchor={weekAnchor}
        onShiftClick={vi.fn()}
      />,
    )
    const labels = screen.getAllByRole('button').map(b => b.textContent)
    expect(labels).toEqual(['09:00 – 13:00', '14:00 – 18:00'])
  })

  it('состояние смены видно в ячейке: идёт — «– идёт» и план в подсказке, закрыта — фактическое время', () => {
    render(
      <WeekResourceGrid
        shifts={[
          // по расписанию, ещё идёт: end_time — плановый конец, а не закрытие
          makeShift({ id: 1, user_id: 1, executor_name: 'А', status: 'active', start_time: '2026-06-10T08:00:00+05:00', end_time: '2026-06-10T17:00:00+05:00' }),
          makeShift({ id: 2, user_id: 2, executor_name: 'Б', status: 'completed', start_time: '2026-06-10T08:00:00+05:00', end_time: '2026-06-10T16:02:00+05:00' }),
          makeShift({ id: 3, user_id: 3, executor_name: 'В', status: 'planned', start_time: '2026-06-11T08:00:00+05:00', end_time: '2026-06-11T17:00:00+05:00' }),
        ]}
        weekAnchor={weekAnchor}
        onShiftClick={vi.fn()}
      />,
    )
    const active = screen.getByText('08:00 – идёт').closest('button')!
    expect(active).toHaveAttribute('data-shift-state', 'active')
    expect(active).toHaveAttribute('title', '08:00 – идёт · план до 17:00 · Активна')
    expect(screen.getByText('08:00 – 16:02').closest('button')).toHaveAttribute('data-shift-state', 'completed')
    expect(screen.getByText('08:00 – 17:00').closest('button')).toHaveAttribute('data-shift-state', 'planned')
  })
})
