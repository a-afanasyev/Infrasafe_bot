import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
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
import CreateShiftModal from '../components/shifts/CreateShiftModal'
import ShiftDetailModal from '../components/shifts/ShiftDetailModal'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { usePageTitle } from '../hooks/usePageTitle'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export default function ShiftsPage() {
  usePageTitle('Смены')
  const navigate = useNavigate()
  const { setActions, clearActions } = useTopbar()
  useShiftsWebSocket()
  const [selectedDate, setSelectedDate] = useState(new Date())
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [selectedShiftId, setSelectedShiftId] = useState<number | null>(null)

  const dateStr = selectedDate.toISOString().split('T')[0]
  const nextDay = new Date(selectedDate)
  nextDay.setDate(nextDay.getDate() + 1)
  const nextDayStr = nextDay.toISOString().split('T')[0]

  const { data: shifts = [], isLoading: shiftsLoading } = useShiftSchedule(
    dateStr + 'T00:00:00Z',
    nextDayStr + 'T00:00:00Z',
  )
  const { data: stats } = useShiftStats()
  const { data: transfers = [] } = useShiftTransfers()
  const { data: templates = [] } = useShiftTemplates()

  const goToday = () => setSelectedDate(new Date())
  const goPrev = () =>
    setSelectedDate(d => {
      const n = new Date(d)
      n.setDate(n.getDate() - 1)
      return n
    })
  const goNext = () =>
    setSelectedDate(d => {
      const n = new Date(d)
      n.setDate(n.getDate() + 1)
      return n
    })

  // Topbar actions
  useEffect(() => {
    setActions(
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate('/dashboard/templates')}
        >
          Шаблоны
        </Button>
        <Button
          size="sm"
          onClick={() => setCreateModalOpen(true)}
        >
          + Создать смену
        </Button>
      </div>,
    )
    return clearActions
  }, [setActions, clearActions])

  if (shiftsLoading) return <LoadingSpinner />

  // Date label in Russian
  const dayNames = [
    'Воскресенье',
    'Понедельник',
    'Вторник',
    'Среда',
    'Четверг',
    'Пятница',
    'Суббота',
  ]
  const monthNames = [
    'января',
    'февраля',
    'марта',
    'апреля',
    'мая',
    'июня',
    'июля',
    'августа',
    'сентября',
    'октября',
    'ноября',
    'декабря',
  ]
  const dateLabelStr = `${dayNames[selectedDate.getDay()]}, ${selectedDate.getDate()} ${monthNames[selectedDate.getMonth()]} ${selectedDate.getFullYear()}`

  const totalLoad =
    shifts.length > 0
      ? Math.round(
          shifts.reduce((s, sh) => s + sh.load_percentage, 0) / shifts.length,
        )
      : 0

  // (no specialization data on ShiftBrief, use active_shifts as proxy)
  const specCoverage = stats ? Math.min(100, Math.round((stats.active_executors / Math.max(stats.active_shifts, 1)) * 100)) : 0

  const STATS_CARDS = [
    { label: 'Исполнителей на смене', value: `${stats?.active_executors ?? 0}`, color: 'var(--accent)' },
    { label: 'Покрытие %', value: `${stats?.coverage_pct ?? 0}%`, color: 'var(--blue)' },
    { label: 'Покрытие спец-ций', value: `${specCoverage}%`, color: 'var(--emerald)' },
    { label: 'Передачи', value: `${stats?.pending_transfers ?? 0}`, color: 'var(--amber)' },
    { label: 'Общая нагрузка', value: `${totalLoad}%`, color: 'var(--violet)' },
  ]

  return (
    <div className="p-5 px-6 flex flex-col gap-5">
      {/* Date navigation */}
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="icon"
          className="w-9 h-9"
          onClick={goPrev}
        >
          <ChevronLeft size={16} />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="w-9 h-9"
          onClick={goNext}
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
          Сегодня
        </button>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-5 gap-3">
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

      {/* Timeline */}
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <div className="px-5 pt-4 pb-3 border-b border-border-default font-[var(--font-display)] font-semibold text-sm text-text-primary">
          Расписание смен
        </div>
        <ShiftTimeline
          shifts={shifts}
          date={selectedDate}
          onShiftClick={s => setSelectedShiftId(s.id)}
        />
      </div>

      {/* Bottom panels */}
      <div className="grid grid-cols-[1fr_380px] gap-5">
        {/* Heatmap */}
        <div className="bg-bg-card border border-border-default rounded-default p-5">
          <div className="font-[var(--font-display)] font-semibold text-sm text-text-primary mb-4">
            Тепловая карта покрытия
          </div>
          <ShiftCoverageHeatmap shifts={shifts} date={selectedDate} />
        </div>

        {/* Transfers + Templates */}
        <div className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-4">
          {/* Transfers */}
          <div className="flex items-center gap-2">
            <span className="font-[var(--font-display)] font-semibold text-sm text-text-primary">
              Запросы на передачу
            </span>
            {transfers.length > 0 && (
              <span className="bg-amber/20 text-amber rounded-full px-2 py-0.5 text-[11px] font-semibold">
                {transfers.length}
              </span>
            )}
          </div>

          {transfers.length === 0 ? (
            <div className="text-[13px] text-text-muted text-center py-3">
              Нет запросов на передачу
            </div>
          ) : (
            transfers.slice(0, 3).map(t => (
              <div
                key={t.id}
                className="flex items-start gap-2 p-2.5 bg-bg-surface rounded-sm"
              >
                <div
                  className={cn(
                    'w-2 h-2 rounded-full mt-1 shrink-0',
                    t.urgency_level === 'critical'
                      ? 'bg-red'
                      : t.urgency_level === 'high'
                        ? 'bg-amber'
                        : 'bg-blue'
                  )}
                />
                <div className="flex-1 overflow-hidden">
                  <div className="text-xs text-text-primary font-semibold truncate">
                    {t.from_executor_name} → {t.to_executor_name ?? '?'}
                  </div>
                  <div className="text-[11px] text-text-muted mt-0.5">
                    {t.reason}
                  </div>
                </div>
              </div>
            ))
          )}

          {/* Templates */}
          <div className="border-t border-border-default pt-3">
            <div className="font-[var(--font-display)] font-semibold text-[13px] text-text-primary mb-2.5">
              Шаблоны смен
            </div>
            {templates.slice(0, 3).map(tmpl => (
              <div
                key={tmpl.id}
                className="flex items-center gap-2.5 py-2 border-b border-border-default"
              >
                <div className="w-8 h-8 rounded-sm bg-accent-dim flex items-center justify-center text-base shrink-0">
                  📋
                </div>
                <div className="flex-1 overflow-hidden">
                  <div className="text-xs font-semibold text-text-primary truncate">
                    {tmpl.name}
                  </div>
                  <div className="text-[11px] text-text-muted">
                    {`${tmpl.start_hour}:${String(tmpl.start_minute).padStart(2, '0')} · ${tmpl.duration_hours}ч`}
                  </div>
                </div>
              </div>
            ))}
            {templates.length === 0 && (
              <div className="text-xs text-text-muted">
                Нет шаблонов
              </div>
            )}
          </div>
        </div>
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
