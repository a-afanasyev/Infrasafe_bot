import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { useTopbar } from '../contexts/TopbarContext'
import {
  useShiftSchedule,
  useShiftStats,
  useShiftTransfers,
  useShiftTemplates,
  useShiftsWebSocket,
} from '../hooks/useShifts'
import ShiftTimeline from '../components/shifts/ShiftTimeline'
import ShiftCoverageHeatmap from '../components/shifts/ShiftCoverageHeatmap'
import WeekResourceGrid from '../components/shifts/WeekResourceGrid'
import MonthResourceGrid from '../components/shifts/MonthResourceGrid'
import SpecializationSidebar from '../components/shifts/SpecializationSidebar'
import CalendarHeatmap from '../components/shifts/CalendarHeatmap'
import ShiftViewToggle, { type ShiftViewMode } from '../components/shifts/ShiftViewToggle'
import CreateShiftModal from '../components/shifts/CreateShiftModal'
import ShiftDetailModal from '../components/shifts/ShiftDetailModal'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { usePageTitle } from '../hooks/usePageTitle'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  addDays,
  endOfMonth,
  endOfWeek,
  startOfDay,
  startOfMonth,
  startOfWeek,
} from '../utils/shiftWeek'

const DAY_KEYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const
const MONTH_KEYS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'] as const

function toIsoLocalMidnight(d: Date): string {
  // Match the existing convention used for day-view: YYYY-MM-DDT00:00:00Z.
  return `${d.toISOString().split('T')[0]}T00:00:00Z`
}

export default function ShiftsPage() {
  const { t } = useTranslation()
  usePageTitle(t('nav.shifts'))
  const navigate = useNavigate()
  const { setActions, clearActions } = useTopbar()
  useShiftsWebSocket()
  const [viewMode, setViewMode] = useState<ShiftViewMode>('day')
  const [selectedDate, setSelectedDate] = useState(new Date())
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [selectedShiftId, setSelectedShiftId] = useState<number | null>(null)
  // Spec filter is "month view only" but lifted to the page so switching views
  // keeps the selection sticky if the user toggles month → week → month.
  const [selectedSpec, setSelectedSpec] = useState<string | null>(null)

  // Compute the [dateFrom, dateTo) range to fetch based on view mode.
  // Day view keeps the original behavior; week pulls Mon..Sun; month pulls
  // [first..last+1) of the month containing selectedDate.
  const { dateFrom, dateTo } = useMemo(() => {
    if (viewMode === 'day') {
      const start = startOfDay(selectedDate)
      return { dateFrom: start, dateTo: addDays(start, 1) }
    }
    if (viewMode === 'week') {
      return { dateFrom: startOfWeek(selectedDate), dateTo: endOfWeek(selectedDate) }
    }
    return { dateFrom: startOfMonth(selectedDate), dateTo: endOfMonth(selectedDate) }
  }, [viewMode, selectedDate])

  const { data: shifts = [], isLoading: shiftsLoading } = useShiftSchedule(
    toIsoLocalMidnight(dateFrom),
    toIsoLocalMidnight(dateTo),
  )
  const { data: stats } = useShiftStats()
  const { data: transfers = [] } = useShiftTransfers()
  const { data: templates = [] } = useShiftTemplates()

  const goToday = () => setSelectedDate(new Date())
  const goPrev = () =>
    setSelectedDate(d => {
      if (viewMode === 'month') {
        const n = new Date(d)
        n.setMonth(n.getMonth() - 1)
        return n
      }
      const step = viewMode === 'week' ? 7 : 1
      return addDays(d, -step)
    })
  const goNext = () =>
    setSelectedDate(d => {
      if (viewMode === 'month') {
        const n = new Date(d)
        n.setMonth(n.getMonth() + 1)
        return n
      }
      const step = viewMode === 'week' ? 7 : 1
      return addDays(d, step)
    })

  useEffect(() => {
    setActions(
      <div className="flex gap-2 items-center">
        <ShiftViewToggle value={viewMode} onChange={setViewMode} />
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate('/dashboard/templates')}
        >
          {t('nav.templates')}
        </Button>
        <Button
          size="sm"
          onClick={() => setCreateModalOpen(true)}
        >
          {t('shifts.createShift')}
        </Button>
      </div>,
    )
    return clearActions
  }, [setActions, clearActions, t, viewMode, navigate])

  if (shiftsLoading) return <LoadingSpinner />

  // ── Date label — adapts to view mode.
  let dateLabelStr = ''
  if (viewMode === 'day') {
    dateLabelStr = `${t(`days.full.${DAY_KEYS[selectedDate.getDay()]}`)}, ${selectedDate.getDate()} ${t(`months.${MONTH_KEYS[selectedDate.getMonth()]}`)} ${selectedDate.getFullYear()}`
  } else if (viewMode === 'week') {
    const wkStart = startOfWeek(selectedDate)
    const wkEnd = addDays(wkStart, 6)
    const sameMonth = wkStart.getMonth() === wkEnd.getMonth()
    const fromStr = sameMonth
      ? `${wkStart.getDate()}`
      : `${wkStart.getDate()} ${t(`months.${MONTH_KEYS[wkStart.getMonth()]}`)}`
    const toStr = `${wkEnd.getDate()} ${t(`months.${MONTH_KEYS[wkEnd.getMonth()]}`)} ${wkEnd.getFullYear()}`
    dateLabelStr = t('shifts.weekLabel', { from: fromStr, to: toStr })
  } else {
    dateLabelStr = `${t(`months.${MONTH_KEYS[selectedDate.getMonth()]}`)} ${selectedDate.getFullYear()}`
  }

  const totalLoad =
    shifts.length > 0
      ? Math.round(
          shifts.reduce((s, sh) => s + sh.load_percentage, 0) / shifts.length,
        )
      : 0

  const specCoverage = stats ? Math.min(100, Math.round((stats.active_executors / Math.max(stats.active_shifts, 1)) * 100)) : 0

  const STATS_CARDS = [
    { label: t('analytics.executorsOnShift'), value: `${stats?.active_executors ?? 0}`, color: 'var(--accent)' },
    { label: t('analytics.coveragePct'), value: `${stats?.coverage_pct ?? 0}%`, color: 'var(--blue)' },
    { label: t('analytics.specCoverage'), value: `${specCoverage}%`, color: 'var(--emerald)' },
    { label: t('shifts.transfers'), value: `${stats?.pending_transfers ?? 0}`, color: 'var(--amber)' },
    { label: t('analytics.totalLoad'), value: `${totalLoad}%`, color: 'var(--violet)' },
  ]

  const todayLabel =
    viewMode === 'week'
      ? t('shifts.thisWeek')
      : viewMode === 'month'
        ? t('shifts.thisMonth')
        : t('shifts.today')

  return (
    <div className="p-5 px-6 flex flex-col gap-5">
      {/* Date navigation */}
      <div className="flex items-center gap-3 flex-wrap">
        <Button
          variant="outline"
          size="icon"
          className="w-9 h-9"
          onClick={goPrev}
          aria-label={
            viewMode === 'month'
              ? t('shifts.prevMonth')
              : viewMode === 'week'
                ? t('shifts.prevWeek')
                : t('shifts.today')
          }
        >
          <ChevronLeft size={16} />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="w-9 h-9"
          onClick={goNext}
          aria-label={
            viewMode === 'month'
              ? t('shifts.nextMonth')
              : viewMode === 'week'
                ? t('shifts.nextWeek')
                : t('shifts.today')
          }
        >
          <ChevronRight size={16} />
        </Button>
        <span className="font-[var(--font-display)] font-semibold text-base text-text-primary">
          {dateLabelStr}
        </span>
        <button
          onClick={goToday}
          className="px-3 py-1 rounded-full bg-accent-dim text-accent border border-border-active text-xs font-semibold cursor-pointer"
        >
          {todayLabel}
        </button>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {STATS_CARDS.map(card => (
          <div
            key={card.label}
            className="bg-bg-card border border-border-default rounded-default p-4 relative overflow-hidden"
          >
            <div
              className="font-[var(--font-mono)] text-2xl font-semibold mb-1"
              style={{ color: card.color }}
            >
              {card.value}
            </div>
            <div className="text-[11px] text-text-muted">
              {card.label}
            </div>
            <div
              className="absolute bottom-0 left-0 right-0 h-[3px] opacity-40"
              style={{ background: card.color }}
            />
          </div>
        ))}
      </div>

      {/* View body */}
      {viewMode === 'day' ? (
        <DayView shifts={shifts} date={selectedDate} onShiftClick={s => setSelectedShiftId(s.id)} />
      ) : viewMode === 'week' ? (
        <WeekView
          shifts={shifts}
          weekAnchor={selectedDate}
          onShiftClick={s => setSelectedShiftId(s.id)}
        />
      ) : (
        <MonthView
          shifts={shifts}
          monthAnchor={selectedDate}
          selectedSpec={selectedSpec}
          onSelectSpec={setSelectedSpec}
          onShiftClick={s => setSelectedShiftId(s.id)}
          onDayClick={day => {
            setSelectedDate(day)
            setViewMode('week')
          }}
        />
      )}

      {/* Bottom panels — kept consistent across views for context. */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-5">
        {/* Transfers + Templates */}
        <div className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <span className="font-[var(--font-display)] font-semibold text-sm text-text-primary">
              {t('shifts.transferRequests')}
            </span>
            {transfers.length > 0 && (
              <span className="bg-amber/20 text-amber rounded-full px-2 py-0.5 text-[11px] font-semibold">
                {transfers.length}
              </span>
            )}
          </div>

          {transfers.length === 0 ? (
            <div className="text-[13px] text-text-muted text-center py-3">
              {t('shifts.noTransfers')}
            </div>
          ) : (
            transfers.slice(0, 3).map(tr => (
              <div
                key={tr.id}
                className="flex items-start gap-2 p-2.5 bg-bg-surface rounded-sm"
              >
                <div
                  className={cn(
                    'w-2 h-2 rounded-full mt-1 shrink-0',
                    tr.urgency_level === 'critical'
                      ? 'bg-red'
                      : tr.urgency_level === 'high'
                        ? 'bg-amber'
                        : 'bg-blue',
                  )}
                />
                <div className="flex-1 overflow-hidden">
                  <div className="text-xs text-text-primary font-semibold truncate">
                    {tr.from_executor_name} → {tr.to_executor_name ?? '?'}
                  </div>
                  <div className="text-[11px] text-text-muted mt-0.5">
                    {t(`transferReason.${tr.reason}`, tr.reason)}
                  </div>
                </div>
              </div>
            ))
          )}

          <div className="border-t border-border-default pt-3">
            <div className="font-[var(--font-display)] font-semibold text-[13px] text-text-primary mb-2.5">
              {t('shifts.shiftTemplates')}
            </div>
            {templates.slice(0, 3).map(tmpl => (
              <div
                key={tmpl.id}
                className="flex items-center gap-2.5 py-2 border-b border-border-default"
              >
                <div className="w-8 h-8 rounded-sm bg-accent-dim flex items-center justify-center text-base shrink-0">
                  {'\u{1F4CB}'}
                </div>
                <div className="flex-1 overflow-hidden">
                  <div className="text-xs font-semibold text-text-primary truncate">
                    {tmpl.name}
                  </div>
                  <div className="text-[11px] text-text-muted">
                    {`${tmpl.start_hour}:${String(tmpl.start_minute).padStart(2, '0')} · ${tmpl.duration_hours}${t('analytics.h')}`}
                  </div>
                </div>
              </div>
            ))}
            {templates.length === 0 && (
              <div className="text-xs text-text-muted">
                {t('shifts.noTemplates')}
              </div>
            )}
          </div>
        </div>

        {/* Heatmap (day-only — week/month get their own coverage views) */}
        {viewMode === 'day' && (
          <div className="bg-bg-card border border-border-default rounded-default p-5">
            <div className="font-[var(--font-display)] font-semibold text-sm text-text-primary mb-4">
              {t('shifts.coverageHeatmap')}
            </div>
            <ShiftCoverageHeatmap shifts={shifts} date={selectedDate} />
          </div>
        )}
      </div>

      {/* Modals */}
      <CreateShiftModal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
      />
      <ShiftDetailModal
        shiftId={selectedShiftId}
        onClose={() => setSelectedShiftId(null)}
      />
    </div>
  )
}

// ─── View renderers ──────────────────────────────────────────────────────

interface ViewBodyProps {
  shifts: import('../hooks/useShifts').ShiftBrief[]
  onShiftClick: (s: import('../hooks/useShifts').ShiftBrief) => void
}

function DayView({ shifts, date, onShiftClick }: ViewBodyProps & { date: Date }) {
  const { t } = useTranslation()
  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <div className="px-5 pt-4 pb-3 border-b border-border-default font-[var(--font-display)] font-semibold text-sm text-text-primary">
        {t('shifts.shiftSchedule')}
      </div>
      <ShiftTimeline shifts={shifts} date={date} onShiftClick={onShiftClick} />
    </div>
  )
}

function WeekView({ shifts, weekAnchor, onShiftClick }: ViewBodyProps & { weekAnchor: Date }) {
  const { t } = useTranslation()
  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <div className="px-5 pt-4 pb-3 border-b border-border-default font-[var(--font-display)] font-semibold text-sm text-text-primary">
        {t('shifts.shiftSchedule')}
      </div>
      <WeekResourceGrid
        shifts={shifts}
        weekAnchor={weekAnchor}
        onShiftClick={onShiftClick}
      />
    </div>
  )
}

interface MonthViewProps {
  shifts: import('../hooks/useShifts').ShiftBrief[]
  monthAnchor: Date
  selectedSpec: string | null
  onSelectSpec: (spec: string | null) => void
  onShiftClick: (s: import('../hooks/useShifts').ShiftBrief) => void
  onDayClick: (day: Date) => void
}

function MonthView({
  shifts,
  monthAnchor,
  selectedSpec,
  onSelectSpec,
  onShiftClick,
  onDayClick,
}: MonthViewProps) {
  const { t } = useTranslation()
  return (
    <div className="flex gap-4 items-start">
      <SpecializationSidebar
        shifts={shifts}
        selectedSpec={selectedSpec}
        onSelectSpec={onSelectSpec}
      />
      <div className="flex-1 min-w-0 flex flex-col gap-4">
        <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
          <div className="px-5 pt-4 pb-3 border-b border-border-default font-[var(--font-display)] font-semibold text-sm text-text-primary">
            {t('shifts.shiftSchedule')}
          </div>
          <MonthResourceGrid
            shifts={shifts}
            monthAnchor={monthAnchor}
            selectedSpec={selectedSpec}
            onShiftClick={onShiftClick}
          />
        </div>
        <div className="bg-bg-card border border-border-default rounded-default p-5">
          <div className="font-[var(--font-display)] font-semibold text-sm text-text-primary mb-4">
            {t('shifts.monthHeatmapTitle')}
          </div>
          <CalendarHeatmap
            shifts={shifts}
            monthAnchor={monthAnchor}
            onDayClick={onDayClick}
          />
        </div>
      </div>
    </div>
  )
}
