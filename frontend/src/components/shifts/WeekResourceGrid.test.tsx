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
