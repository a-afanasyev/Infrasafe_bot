import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import type { ShiftBrief } from '../../hooks/useShifts'
import { specColor } from '../../utils/shiftWeek'
import { cn } from '@/lib/utils'

/**
 * Sidebar that groups the month's shifts by `specialization_focus`.
 * Selection is single (or null = "Все"); selecting a spec drives the
 * `MonthResourceGrid` filter and updates the sidebar totals.
 *
 * Implementation note: the sidebar is the source of truth for which spec is
 * selected — `MonthResourceGrid` is purely controlled by `selectedSpec`.
 */
interface Props {
  shifts: ShiftBrief[]
  selectedSpec: string | null
  onSelectSpec: (spec: string | null) => void
}

const UNSPECIFIED_KEY = '__unspecified__'

interface SpecRow {
  key: string
  label: string
  isUnspecified: boolean
  executorCount: number
  shiftCount: number
  totalHours: number
}

function shiftDurationHours(shift: ShiftBrief): number {
  if (!shift.end_time) return 0
  const startMs = new Date(shift.start_time).getTime()
  const endMs = new Date(shift.end_time).getTime()
  if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs <= startMs) return 0
  return (endMs - startMs) / 3_600_000
}

export default function SpecializationSidebar({
  shifts,
  selectedSpec,
  onSelectSpec,
}: Props) {
  const { t } = useTranslation()

  const { rows, totals } = useMemo(() => {
    // Group shifts by spec. A shift with multiple specs counts in each;
    // a shift with no spec lands in `__unspecified__`. Executors are
    // deduped per spec via a Set.
    const buckets = new Map<string, { executors: Set<string>; shiftCount: number; totalHours: number; label: string; isUnspecified: boolean }>()

    const ensure = (key: string, label: string, isUnspecified: boolean) => {
      const existing = buckets.get(key)
      if (existing) return existing
      const created = { executors: new Set<string>(), shiftCount: 0, totalHours: 0, label, isUnspecified }
      buckets.set(key, created)
      return created
    }

    for (const shift of shifts) {
      const execKey = shift.executor_name || (shift.user_id ? `user_${shift.user_id}` : `shift_${shift.id}`)
      const hours = shiftDurationHours(shift)
      const specs = (shift.specialization_focus ?? []).filter(Boolean)
      if (specs.length === 0) {
        const bucket = ensure(UNSPECIFIED_KEY, t('shifts.specSidebar.unspecified'), true)
        bucket.executors.add(execKey)
        bucket.shiftCount += 1
        bucket.totalHours += hours
        continue
      }
      for (const spec of specs) {
        const bucket = ensure(spec, spec, false)
        bucket.executors.add(execKey)
        bucket.shiftCount += 1
        bucket.totalHours += hours
      }
    }

    const rowList: SpecRow[] = Array.from(buckets.entries()).map(([key, b]) => ({
      key,
      label: b.label,
      isUnspecified: b.isUnspecified,
      executorCount: b.executors.size,
      shiftCount: b.shiftCount,
      totalHours: Math.round(b.totalHours),
    }))
    // Sort: specified specs (alpha), then "Универсалы" at bottom.
    rowList.sort((a, b) => {
      if (a.isUnspecified !== b.isUnspecified) return a.isUnspecified ? 1 : -1
      return a.label.localeCompare(b.label)
    })

    // "All" totals (dedup executors globally — same person on different specs
    // still counts once).
    const allExecutors = new Set<string>()
    let allShifts = 0
    let allHours = 0
    for (const shift of shifts) {
      const execKey = shift.executor_name || (shift.user_id ? `user_${shift.user_id}` : `shift_${shift.id}`)
      allExecutors.add(execKey)
      allShifts += 1
      allHours += shiftDurationHours(shift)
    }

    return {
      rows: rowList,
      totals: {
        executorCount: allExecutors.size,
        shiftCount: allShifts,
        totalHours: Math.round(allHours),
      },
    }
  }, [shifts, t])

  return (
    <aside
      className="w-[220px] shrink-0 bg-bg-card border border-border-default rounded-default p-3 flex flex-col gap-2"
      aria-label={t('shifts.specSidebar.title')}
    >
      <div className="px-2 py-1 font-[var(--font-display)] font-semibold text-xs text-text-muted uppercase tracking-wider">
        {t('shifts.specSidebar.title')}
      </div>

      <SidebarItem
        active={selectedSpec === null}
        color="var(--accent)"
        label={t('shifts.specSidebar.all')}
        count={totals.executorCount}
        onClick={() => onSelectSpec(null)}
      />

      {rows.map(row => (
        <SidebarItem
          key={row.key}
          active={selectedSpec === row.key || (selectedSpec === '' && row.isUnspecified)}
          color={row.isUnspecified ? 'var(--text-muted)' : specColor(row.label)}
          label={row.label}
          count={row.executorCount}
          onClick={() => onSelectSpec(row.isUnspecified ? '' : row.key)}
        />
      ))}

      <div className="mt-2 pt-2 border-t border-border-default px-2 text-[11px] text-text-muted leading-relaxed">
        {t('shifts.specSidebar.summary', { shifts: totals.shiftCount, hours: totals.totalHours })}
      </div>
    </aside>
  )
}

interface SidebarItemProps {
  active: boolean
  color: string
  label: string
  count: number
  onClick: () => void
}

function SidebarItem({ active, color, label, count, onClick }: SidebarItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'flex items-center gap-2 px-2 py-1.5 rounded-sm text-xs text-left transition-colors',
        active
          ? 'bg-accent-dim text-accent border border-border-active'
          : 'text-text-secondary hover:bg-bg-card-hover hover:text-text-primary border border-transparent',
      )}
    >
      <span
        aria-hidden
        className="w-2.5 h-2.5 rounded-full shrink-0"
        style={{ background: color }}
      />
      <span className="flex-1 truncate font-semibold">{label}</span>
      <span className="font-[var(--font-mono)] text-[11px] text-text-muted">
        {count}
      </span>
    </button>
  )
}

export { UNSPECIFIED_KEY }
