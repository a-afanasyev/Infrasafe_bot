import { useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, CalendarDays } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { usePageTitle } from '../../hooks/usePageTitle'
import { useAllOccurrences } from '../../hooks/useElevatorCalendar'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import EmptyState from '../../components/shared/EmptyState'
import { fmtDateOnly, isoDatePlusDays } from '../../utils/elevatorsFormat'
import type { ElevatorOccurrence } from '../../types/elevators'

/**
 * Общий календарь (/dashboard/elevators/calendar): все planned записи графика
 * на диапазон дат (по умолчанию 60 дней вперёд), сгруппированные по дате.
 */
const DEFAULT_WINDOW_DAYS = 60

function groupByDate(items: ElevatorOccurrence[]): Array<[string, ElevatorOccurrence[]]> {
  const map = new Map<string, ElevatorOccurrence[]>()
  for (const item of items) {
    map.set(item.due_on, [...(map.get(item.due_on) ?? []), item])
  }
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
}

export default function ElevatorsCalendarPage() {
  const { t } = useTranslation()
  usePageTitle(t('elevators.calendar.title'))
  const [from, setFrom] = useState(() => isoDatePlusDays(0))
  const [to, setTo] = useState(() => isoDatePlusDays(DEFAULT_WINDOW_DAYS))
  const occurrences = useAllOccurrences({ from, to, state: 'planned' })
  const groups = groupByDate(occurrences.data ?? [])

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button asChild variant="outline" size="sm">
            <Link to="/dashboard/elevators" aria-label={t('elevators.actions.backToList')}><ArrowLeft size={15} /></Link>
          </Button>
          <CalendarDays className="text-accent" size={22} />
          <div>
            <h1 className="text-xl font-semibold text-text-primary">{t('elevators.calendar.title')}</h1>
            <p className="text-[13px] text-text-muted">{t('elevators.calendar.subtitle')}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="elevators-cal-from">{t('elevators.calendar.from')}</Label>
            <Input id="elevators-cal-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="elevators-cal-to">{t('elevators.calendar.to')}</Label>
            <Input id="elevators-cal-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </div>
      </div>

      {occurrences.isLoading ? (
        <LoadingSpinner />
      ) : occurrences.isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : groups.length === 0 ? (
        <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
          <EmptyState icon="🗓️" title={t('elevators.calendar.empty')} />
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map(([date, items]) => (
            <div key={date} className="bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-2">
              <h2 className="text-[13px] font-semibold text-text-primary">{fmtDateOnly(date)}</h2>
              <ul className="flex flex-col gap-1.5">
                {items.map((o) => (
                  <li key={o.id} className="flex flex-wrap items-center gap-2 text-[13px]">
                    <span className="rounded-full bg-bg-surface text-text-secondary text-[11px] px-2 py-0.5">
                      {t(`elevators.occurrences.kind.${o.kind}`)}
                    </span>
                    <Link to={`/dashboard/elevators/${o.elevator_id}`} className="font-semibold text-accent hover:underline">
                      {o.elevator_label}
                    </Link>
                    {o.comment && <span className="text-text-muted truncate max-w-64">{o.comment}</span>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
