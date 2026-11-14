import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import { ru, uz } from 'date-fns/locale'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useNotices, type Notice } from '../../hooks/useNotices'
import { formatTime, todayInDisplayTz } from '../../utils/timezone'
import { eventsByDay, gridWindow, monthGrid, type CalendarTone } from './noticeModel'

interface Props {
  onOpen: (notice: Notice) => void
  /** Клик по дню: создать запись на эту дату (YYYY-MM-DD). */
  onPickDay: (day: string) => void
}

// Цвет — по виду записи; оттенки нейтральны к бренду (акцент — только «новость»).
const TONE: Record<CalendarTone, string> = {
  news: 'bg-accent-dim text-accent',
  outage: 'bg-amber-500/15 text-amber-600',
  staff: 'bg-sky-500/15 text-sky-600',
  channel: 'bg-blue-500/15 text-blue-600',
  pending: 'border border-dashed border-border-default text-text-muted',
}
const LEGEND: CalendarTone[] = ['news', 'outage', 'staff', 'channel', 'pending']
const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const
const MAX_PER_DAY = 3

/** Календарь публикаций и отключений: месяц, клик по дню — создать, по записи — открыть. */
export default function NoticeCalendar({ onOpen, onPickDay }: Props) {
  const { t, i18n } = useTranslation()
  const today = todayInDisplayTz()
  const [cursor, setCursor] = useState(() => ({ year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)) - 1 }))
  const days = useMemo(() => monthGrid(cursor.year, cursor.month), [cursor])
  // Свой запрос по видимой сетке: лента отдаёт только свежие записи, а в
  // календаре нужны все события месяца, включая давно созданные.
  const range = useMemo(() => gridWindow(days), [days])
  const notices = useNotices(range)
  const events = useMemo(() => eventsByDay(notices.data?.items ?? []), [notices.data])
  const shift = (delta: number) => setCursor(({ year, month }) => {
    const d = new Date(year, month + delta, 1)
    return { year: d.getFullYear(), month: d.getMonth() }
  })
  // date-fns, а не Intl: набор локалей браузера не гарантирован (uz часто нет).
  const monthLabel = format(new Date(cursor.year, cursor.month, 1), 'LLLL yyyy', { locale: i18n.language.startsWith('uz') ? uz : ru })
  const monthPrefix = `${cursor.year}-${String(cursor.month + 1).padStart(2, '0')}`

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Button variant="outline" size="icon" aria-label={t('notices.calendar.prev')} onClick={() => shift(-1)}><ChevronLeft size={16} /></Button>
        <h2 className="min-w-40 text-center text-sm font-semibold capitalize text-text-primary">{monthLabel}</h2>
        <Button variant="outline" size="icon" aria-label={t('notices.calendar.next')} onClick={() => shift(1)}><ChevronRight size={16} /></Button>
      </div>

      <div className="overflow-x-auto">
        <div className="grid min-w-[640px] grid-cols-[repeat(7,minmax(0,1fr))] gap-px overflow-hidden rounded-default border border-border-default bg-border-default">
          {DAYS.map((d) => (
            <div key={d} className="bg-bg-surface px-2 py-1.5 text-[11px] font-bold uppercase text-text-muted">{t(`days.short.${d}`)}</div>
          ))}
          {days.map((day) => {
            const list = events.get(day) ?? []
            return (
              <div
                key={day}
                data-day={day}
                role="button"
                tabIndex={0}
                aria-label={t('notices.calendar.createOn', { day })}
                onClick={() => onPickDay(day)}
                onKeyDown={(e) => { if (e.key === 'Enter' && e.target === e.currentTarget) onPickDay(day) }}
                className={cn(
                  'min-h-[84px] cursor-pointer bg-bg-card p-1.5 text-left hover:bg-bg-card-hover',
                  !day.startsWith(monthPrefix) && 'opacity-45',
                  day === today && 'bg-accent-dim/40',
                )}
              >
                <div className={cn('mb-1 text-xs font-bold', day === today ? 'text-accent' : 'text-text-primary')}>
                  {Number(day.slice(8))}
                </div>
                {list.slice(0, MAX_PER_DAY).map((ev, i) => (
                  <button
                    key={`${ev.notice.id}-${i}`}
                    type="button"
                    title={ev.notice.title_ru}
                    onClick={(e) => { e.stopPropagation(); onOpen(ev.notice) }}
                    className={cn('mb-0.5 block w-full truncate rounded-[4px] px-1 py-px text-left text-[11px] font-semibold', TONE[ev.tone])}
                  >
                    {ev.at && !ev.notice.all_day ? `${formatTime(ev.at)} ` : ''}{ev.notice.title_ru}
                  </button>
                ))}
                {list.length > MAX_PER_DAY && (
                  <div className="text-[10px] text-text-muted">{t('notices.calendar.more', { n: list.length - MAX_PER_DAY })}</div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        {LEGEND.map((tone) => (
          <span key={tone} className="flex items-center gap-1.5">
            <span className={cn('inline-block h-3 w-3 rounded-[3px]', TONE[tone])} />
            {t(`notices.calendar.legend.${tone}`)}
          </span>
        ))}
      </div>
      <p className="text-xs text-text-muted">
        {notices.isError ? t('common.error') : t('notices.calendar.hint')}
      </p>
    </div>
  )
}
