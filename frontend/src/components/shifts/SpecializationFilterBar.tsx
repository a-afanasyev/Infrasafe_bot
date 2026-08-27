import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import type { ShiftBrief } from '../../hooks/useShifts'
import { tSpecialization } from '../../i18n/apiMaps'
import { executorKey, specColor, UNSPECIFIED_SPEC_KEY } from '../../utils/shiftWeek'
import { cn } from '@/lib/utils'

/**
 * Горизонтальная полоса-фильтр по `specialization_focus` над расписанием
 * месяца (решение владельца 2026-08-27: прежний вертикальный сайдбар слева
 * съедал ширину у таблицы). Выбор одиночный (null = «Все»); выбранная
 * специализация управляет фильтром `MonthResourceGrid`.
 *
 * Полоса — source of truth выбранной специализации, грид ею управляется.
 */
interface Props {
  shifts: ShiftBrief[]
  selectedSpec: string | null
  onSelectSpec: (spec: string | null) => void
}

interface SpecRow {
  key: string
  label: string
  isUnspecified: boolean
  executorCount: number
}

function shiftDurationHours(shift: ShiftBrief): number {
  if (!shift.end_time) return 0
  const startMs = new Date(shift.start_time).getTime()
  const endMs = new Date(shift.end_time).getTime()
  if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs <= startMs) return 0
  return (endMs - startMs) / 3_600_000
}

export default function SpecializationFilterBar({
  shifts,
  selectedSpec,
  onSelectSpec,
}: Props) {
  const { t } = useTranslation()

  const { rows, totals } = useMemo(() => {
    // Группировка смен по специализации. Смена с несколькими — в каждой;
    // без специализации — в «Универсалы». Исполнители дедупятся Set-ом.
    const buckets = new Map<string, { executors: Set<string>; label: string; isUnspecified: boolean }>()

    const ensure = (key: string, label: string, isUnspecified: boolean) => {
      const existing = buckets.get(key)
      if (existing) return existing
      const created = { executors: new Set<string>(), label, isUnspecified }
      buckets.set(key, created)
      return created
    }

    for (const shift of shifts) {
      const execKey = executorKey(shift)
      const specs = (shift.specialization_focus ?? []).filter(Boolean)
      if (specs.length === 0) {
        ensure(UNSPECIFIED_SPEC_KEY, t('shifts.specSidebar.unspecified'), true).executors.add(execKey)
        continue
      }
      for (const spec of specs) {
        // Метка — локализованная (RU/UZ), ключ и ЦВЕТ — от сырого канон-токена:
        // грид красит точки по сырому ключу, и хэш-палитра обязана совпадать.
        ensure(spec, tSpecialization(spec, t), false).executors.add(execKey)
      }
    }

    const rowList: SpecRow[] = Array.from(buckets.entries()).map(([key, b]) => ({
      key,
      label: b.label,
      isUnspecified: b.isUnspecified,
      executorCount: b.executors.size,
    }))
    // Сортировка: именованные специализации по алфавиту, «Универсалы» в конце.
    rowList.sort((a, b) => {
      if (a.isUnspecified !== b.isUnspecified) return a.isUnspecified ? 1 : -1
      return a.label.localeCompare(b.label)
    })

    // Итоги «Все» (исполнители дедупятся глобально).
    const allExecutors = new Set<string>()
    let allHours = 0
    for (const shift of shifts) {
      allExecutors.add(executorKey(shift))
      allHours += shiftDurationHours(shift)
    }

    return {
      rows: rowList,
      totals: {
        executorCount: allExecutors.size,
        shiftCount: shifts.length,
        totalHours: Math.round(allHours),
      },
    }
  }, [shifts, t])

  return (
    <div
      className="bg-bg-card border border-border-default rounded-default px-3 py-2 flex items-center gap-2 flex-wrap"
      role="toolbar"
      aria-label={t('shifts.specSidebar.title')}
    >
      <span className="font-[var(--font-display)] font-semibold text-[11px] text-text-muted uppercase tracking-wider px-1">
        {t('shifts.specSidebar.title')}
      </span>

      <FilterChip
        active={selectedSpec === null}
        color="var(--accent)"
        label={t('shifts.specSidebar.all')}
        count={totals.executorCount}
        onClick={() => onSelectSpec(null)}
      />

      {rows.map(row => (
        <FilterChip
          key={row.key}
          active={selectedSpec === row.key}
          color={row.isUnspecified ? 'var(--text-muted)' : specColor(row.key)}
          label={row.label}
          count={row.executorCount}
          onClick={() => onSelectSpec(row.key)}
        />
      ))}

      <span className="ml-auto text-[11px] text-text-muted whitespace-nowrap pl-2">
        {t('shifts.specSidebar.summary', { shifts: totals.shiftCount, hours: totals.totalHours })}
      </span>
    </div>
  )
}

interface FilterChipProps {
  active: boolean
  color: string
  label: string
  count: number
  onClick: () => void
}

function FilterChip({ active, color, label, count, onClick }: FilterChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-colors',
        active
          ? 'bg-accent-dim text-accent border border-border-active'
          : 'text-text-secondary hover:bg-bg-card-hover hover:text-text-primary border border-border-default',
      )}
    >
      <span aria-hidden className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
      <span className="font-semibold">{label}</span>
      <span className="font-[var(--font-mono)] text-[11px] text-text-muted">{count}</span>
    </button>
  )
}
