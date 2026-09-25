import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '../../test/test-utils'
import CalendarHeatmap from './CalendarHeatmap'
import ShiftTimeline from './ShiftTimeline'
import type { ShiftBrief } from '../../hooks/useShifts'
import { DEFAULT_DISPLAY_TZ, setDisplayTz } from '../../utils/timezone'
import { shiftTypeColor } from '../../utils/shiftWeek'

function hexToRgb(hex: string): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`
}

// TEST-068: месячная тепловая карта и дневная лента смен. Оба считают дни в
// display-tz (Asia/Tashkent), поэтому времена в фикстурах даны с +05:00.

function makeShift(overrides: Partial<ShiftBrief> = {}): ShiftBrief {
  return {
    id: 1,
    user_id: 10,
    executor_name: 'Иван Тестов',
    status: 'active',
    shift_type: 'regular',
    start_time: '2026-06-08T10:00:00+05:00',
    end_time: '2026-06-08T12:00:00+05:00',
    max_requests: 5,
    current_request_count: 0,
    load_percentage: 0,
    specialization_focus: null,
    ...overrides,
  }
}

// Июнь 2026: 1 июня — понедельник, 5 ISO-недель (1–7 … 29–5 июля).
const june = new Date('2026-06-10T12:00:00+05:00')

describe('CalendarHeatmap', () => {
  it('сетка месяца: 7 колонок дней, W1–W5, кнопки только у дней месяца', () => {
    render(<CalendarHeatmap shifts={[]} monthAnchor={june} onDayClick={() => {}} />)
    for (const d of ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']) expect(screen.getByText(d)).toBeInTheDocument()
    expect(screen.getByText('W1')).toBeInTheDocument()
    expect(screen.getByText('W5')).toBeInTheDocument()
    expect(screen.queryByText('W6')).toBeNull()
    // 30 дней июня — 30 кнопок; хвост июля (1–5) — не кнопки.
    expect(screen.getAllByRole('button')).toHaveLength(30)
    expect(screen.getByText('0 смен · 0 ч в месяце')).toBeInTheDocument()
  })

  it('покрытие дня = число разных исполнителей / цель; заголовок ячейки и счётчик', () => {
    const shifts = [
      makeShift({ id: 1, user_id: 10 }),
      makeShift({ id: 2, user_id: 20, executor_name: 'Пётр Второй' }),
      // Тот же исполнитель второй сменой — в счётчик не добавляется.
      makeShift({ id: 3, user_id: 10, start_time: '2026-06-08T14:00:00+05:00', end_time: '2026-06-08T16:00:00+05:00' }),
    ]
    render(<CalendarHeatmap shifts={shifts} monthAnchor={june} coverageTarget={3} onDayClick={() => {}} />)
    const cell = screen.getByTitle('8.6 · 2/3 (67%)')
    expect(cell).toHaveTextContent('8')
    expect(within(cell).getByText('2')).toBeInTheDocument()
    expect(screen.getByTitle('9.6 · 0/3 (0%)')).toBeInTheDocument()
    // 3 смены по 2 ч.
    expect(screen.getByText('3 смен · 6 ч в месяце')).toBeInTheDocument()
  })

  it('ночная смена засчитывается в оба дня; клик по дню отдаёт эту дату', () => {
    const onDayClick = vi.fn()
    render(
      <CalendarHeatmap
        shifts={[makeShift({ start_time: '2026-06-08T20:00:00+05:00', end_time: '2026-06-09T08:00:00+05:00' })]}
        monthAnchor={june}
        coverageTarget={1}
        onDayClick={onDayClick}
      />,
    )
    expect(screen.getByTitle('8.6 · 1/1 (100%)')).toBeInTheDocument()
    expect(screen.getByTitle('9.6 · 1/1 (100%)')).toBeInTheDocument()
    fireEvent.click(screen.getByTitle('9.6 · 1/1 (100%)'))
    expect(onDayClick).toHaveBeenCalledTimes(1)
    const day = onDayClick.mock.calls[0][0] as Date
    expect([day.getDate(), day.getMonth()]).toEqual([9, 5])
  })

  it('цель 0 — покрытие 0 %, без деления на ноль', () => {
    render(<CalendarHeatmap shifts={[makeShift()]} monthAnchor={june} coverageTarget={0} onDayClick={() => {}} />)
    expect(screen.getByTitle('8.6 · 1/0 (0%)')).toBeInTheDocument()
  })
})

describe('ShiftTimeline', () => {
  const day = new Date('2026-06-08T12:00:00+05:00')

  it('без смен — пустое состояние', () => {
    render(<ShiftTimeline shifts={[]} date={day} onShiftClick={() => {}} />)
    expect(screen.getByText('Нет смен')).toBeInTheDocument()
    expect(screen.getByText('Создайте первую смену')).toBeInTheDocument()
  })

  it('смены группируются по исполнителю; блок несёт время, статус и заявки; клик отдаёт смену', () => {
    const onShiftClick = vi.fn()
    const first = makeShift({ id: 1 })
    const second = makeShift({ id: 2, start_time: '2026-06-08T14:00:00+05:00', end_time: '2026-06-08T16:30:00+05:00', current_request_count: 2 })
    const other = makeShift({ id: 3, user_id: 20, executor_name: 'Пётр Второй', status: 'planned' })
    render(<ShiftTimeline shifts={[first, second, other]} date={day} onShiftClick={onShiftClick} />)

    expect(screen.getByText('Исполнитель')).toBeInTheDocument()
    // Два исполнителя — две строки с инициалами.
    expect(screen.getByText('ИТ')).toBeInTheDocument()
    expect(screen.getByText('ПВ')).toBeInTheDocument()
    expect(screen.getAllByText('Иван Тестов')).toHaveLength(1)
    // Заголовок часов 00…23.
    expect(screen.getByText('00')).toBeInTheDocument()
    expect(screen.getByText('23')).toBeInTheDocument()

    expect(screen.getByText('10:00 — 12:00 · Активна')).toBeInTheDocument()
    expect(screen.getByText('14:00 — 16:30 · Активна')).toBeInTheDocument()
    expect(screen.getByText('10:00 — 12:00 · Планируется')).toBeInTheDocument()
    expect(screen.getByText('2/5')).toBeInTheDocument()

    fireEvent.click(screen.getByText('14:00 — 16:30 · Активна'))
    expect(onShiftClick).toHaveBeenCalledWith(second)
  })

  it('блок дня не режет текст по вертикали: строки не сжимаются, высота — минимум, не фикс', () => {
    render(<ShiftTimeline shifts={[makeShift({ id: 1 })]} date={day} onShiftClick={vi.fn()} />)
    const label = screen.getByText('10:00 — 12:00 · Активна')
    // truncate = overflow:hidden → min-height 0: без shrink-0 flex-колонка сжимала строку.
    expect(label.className).toMatch(/\bshrink-0\b/)
    expect(screen.getByText('0/5').className).toMatch(/\bshrink-0\b/)
    const block = label.parentElement as HTMLElement
    expect(block.style.height).toBe('')
    expect(block.style.minHeight).toBe('38px')
  })

  it('открытая смена без конца — одна ячейка со временем начала; смена другого дня блока не даёт', () => {
    const open = makeShift({ id: 1, end_time: null })
    const otherDay = makeShift({ id: 2, user_id: 20, executor_name: 'Пётр Второй', start_time: '2026-06-09T10:00:00+05:00', end_time: '2026-06-09T12:00:00+05:00' })
    render(<ShiftTimeline shifts={[open, otherDay]} date={day} onShiftClick={() => {}} />)
    expect(screen.getByText('10:00 · Активна')).toBeInTheDocument()
    // Строка второго исполнителя есть, блоков у неё нет.
    expect(screen.getByText('Пётр Второй')).toBeInTheDocument()
    expect(screen.queryByText('10:00 — 12:00 · Активна')).toBeNull()
  })

  // A9-P3-19 (класс ARCH-116): «сегодня» и текущий час считались по зоне
  // браузера. Display-зона +14 (Kiritimati): 10:30Z = 00:30 следующих суток —
  // в любой зоне раннера, кроме +14, старый код не подсветил бы час 00.
  it('текущий час и «сегодня» — в display-зоне, а не в зоне браузера', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-06-05T10:30:00Z'))
    setDisplayTz('Pacific/Kiritimati')
    try {
      render(<ShiftTimeline shifts={[makeShift()]} date={new Date(2026, 5, 6)} onShiftClick={() => {}} />)
      expect(screen.getByText('00').className).toContain('text-accent')
      expect(screen.getByText('10').className).not.toContain('text-accent')
    } finally {
      setDisplayTz(DEFAULT_DISPLAY_TZ)
      vi.useRealTimers()
    }
  })

  it('цвет блока — из канона shiftTypeColor()', () => {
    render(<ShiftTimeline shifts={[makeShift({ shift_type: 'emergency' })]} date={day} onShiftClick={() => {}} />)
    const label = screen.getByText('10:00 — 12:00 · Активна')
    expect(label.style.color).toBe(hexToRgb(shiftTypeColor('emergency')))
  })

  it('наведение подсвечивает блок и возвращает фон при уходе', () => {
    render(<ShiftTimeline shifts={[makeShift()]} date={day} onShiftClick={() => {}} />)
    const block = screen.getByText('10:00 — 12:00 · Активна').parentElement as HTMLElement
    const before = block.style.background
    fireEvent.mouseEnter(block)
    expect(block.style.background).not.toBe(before)
    fireEvent.mouseLeave(block)
    expect(block.style.background).toBe(before)
  })
})
