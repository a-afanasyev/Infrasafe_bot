import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import type { ShiftBrief } from '../../hooks/useShifts'
import { toDisplayTz } from '../../utils/timezone'
import { addDays, isSameDay, isWeekend, startOfWeek, weekDays } from '../../utils/shiftWeek'
import { coverageCellColor, COVERAGE_LEGEND } from './ShiftCoverageHeatmap'
import { cn } from '@/lib/utils'

/**
 * Недельная тепловая карта покрытия: 7 строк-дней × 24 часа. Семантика
 * ячейки та же, что у дневной `ShiftCoverageHeatmap` — «сколько смен
 * активно в этот час» — но развёрнута на неделю, так что ночные и
 * многодневные смены видны в обоих днях. Шкала цветов общая (импорт).
 */
interface Props {
  shifts: ShiftBrief[]
  weekAnchor: Date
}

const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const
const HOUR_MS = 3_600_000

/**
 * Один проход по сменам → счётчики [день 0..6][час 0..23]. Курсор идёт
 * почасово от начала смены до конца (эксклюзивно: конец ровно в HH:00 в
 * час HH не попадает — как в дневной карте), инкрементируя только ячейки
 * внутри недели. Смена без end_time считается часовым блоком (конвенция
 * WeekResourceGrid).
 */
function buildWeekCounts(shifts: ShiftBrief[], weekAnchor: Date): number[][] {
  const counts: number[][] = Array.from({ length: 7 }, () => Array(24).fill(0))
  const weekStart = startOfWeek(weekAnchor)
  const weekEnd = addDays(weekStart, 7)
  const days = weekDays(weekAnchor)

  for (const shift of shifts) {
    const start = toDisplayTz(shift.start_time)
    const end = shift.end_time
      ? toDisplayTz(shift.end_time)
      : new Date(start.getTime() + HOUR_MS)

    // Начало часа, содержащего старт смены; клип по границам недели.
    const slot = new Date(start)
    slot.setMinutes(0, 0, 0)
    if (slot < weekStart) slot.setTime(weekStart.getTime())
    const stop = Math.min(end.getTime(), weekEnd.getTime())

    while (slot.getTime() < stop) {
      // День — сравнением календарных полей (не делением миллисекунд):
      // деление ломается, если в браузерной зоне внутри недели DST-переход.
      const dayIdx = days.findIndex(d => isSameDay(d, slot))
      if (dayIdx !== -1) counts[dayIdx][slot.getHours()] += 1
      slot.setTime(slot.getTime() + HOUR_MS)
    }
  }
  return counts
}

export default function WeekCoverageHeatmap({ shifts, weekAnchor }: Props) {
  const { t } = useTranslation()
  const days = useMemo(() => weekDays(weekAnchor), [weekAnchor])
  const counts = useMemo(() => buildWeekCounts(shifts, weekAnchor), [shifts, weekAnchor])
  const today = new Date()

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[720px] flex flex-col gap-[3px]">
        {/* Часовая шкала сверху — метки каждые 6 часов, как в дневной. */}
        <div
          className="grid gap-[3px]"
          style={{ gridTemplateColumns: '64px repeat(24, minmax(18px, 1fr))' }}
        >
          <div />
          {Array.from({ length: 24 }, (_, h) => (
            <div
              key={h}
              className="text-center text-[10px] text-text-muted font-[var(--font-mono)]"
            >
              {h % 6 === 0 ? String(h).padStart(2, '0') : ''}
            </div>
          ))}
        </div>

        {days.map((day, dayIdx) => (
          <div
            key={day.toISOString()}
            className="grid gap-[3px]"
            style={{ gridTemplateColumns: '64px repeat(24, minmax(18px, 1fr))' }}
          >
            <div
              data-testid={`wk-day-label-${dayIdx}`}
              className={cn(
                'flex items-center justify-end pr-2 text-[10px] font-semibold uppercase tracking-wide',
                isSameDay(day, today) ? 'text-accent' : 'text-text-muted',
                isWeekend(day) && 'opacity-80',
              )}
            >
              {t(`days.short.${DAY_KEYS[dayIdx]}`)} {day.getDate()}
            </div>
            {counts[dayIdx].map((count, hour) => (
              <div
                key={hour}
                data-testid={`wk-cell-${dayIdx}-${hour}`}
                title={`${t(`days.short.${DAY_KEYS[dayIdx]}`)} ${day.getDate()} · ${String(hour).padStart(2, '0')}:00 — ${count}`}
                className="h-6 rounded-[4px] flex items-center justify-center"
                style={{ background: coverageCellColor(count) }}
              >
                <span
                  className="text-[9px] font-[var(--font-mono)] font-semibold"
                  style={{
                    color: count > 0 ? 'rgba(255,255,255,0.8)' : 'rgba(239,68,68,0.8)',
                  }}
                >
                  {count}
                </span>
              </div>
            ))}
          </div>
        ))}

        {/* Легенда — общая с дневной картой. */}
        <div className="flex gap-3 items-center pt-2">
          {COVERAGE_LEGEND.map(item => (
            <div key={item.label} className="flex items-center gap-1.5">
              <div
                className="w-3.5 h-3.5 rounded-[3px]"
                style={{ background: item.color }}
              />
              <span className="text-[11px] text-text-muted">{item.label}</span>
            </div>
          ))}
          <span className="text-[11px] text-text-muted ml-1">
            {t('shifts.executorLabel').toLowerCase()}
          </span>
        </div>
      </div>
    </div>
  )
}
