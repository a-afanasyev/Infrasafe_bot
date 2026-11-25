import { useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { formatTime } from '../../utils/timezone'
import { usePageTitle } from '../../hooks/usePageTitle'
import { usePersonName } from '../../hooks/usePersonName'
import {
  useCleaningComplaints,
  useCleaningRules,
  useCleaningTasks,
  useCleaningTimesheet,
  useDecideCleaningComplaint,
  useSaveCleaningRules,
} from '../../hooks/useCleaning'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import { addDays, isoDate, mondayOf, monthRange, shortDate } from '../../features/cleaning/dates'
import type { CleaningRules, CleaningTaskRow, CleaningTaskStatus } from '../../types/cleaning'

/**
 * Контроль уборки (/dashboard/cleaning/control, manager): план и факт по
 * подъездам за неделю, очередь на проверку, жалобы жителей, табель и настройки.
 * Визиты без замечаний система принимает сама — человеку остаётся очередь.
 */
const CARD = 'bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-3'
const STATUS_CLASS: Record<CleaningTaskStatus, string> = {
  planned: 'text-text-muted',
  in_progress: 'text-blue font-semibold',
  accepted: 'text-green font-semibold',
  review: 'text-amber font-semibold underline',
  rejected: 'text-red font-semibold',
  missed: 'text-red font-semibold',
  expired: 'text-red font-semibold',
}

function RulesForm({ rules }: { rules: CleaningRules }) {
  const { t } = useTranslation()
  const save = useSaveCleaningRules()
  const [dayEnd, setDayEnd] = useState(String(rules.data.day_end_time))
  const [sample, setSample] = useState(String(rules.data.sample_every))
  const [ttl, setTtl] = useState(String(rules.data.session_ttl_minutes))
  const [deferred, setDeferred] = useState(Boolean(rules.data.allow_deferred_auto))
  const numbers = [Number(sample), Number(ttl)]
  const valid = /^([01]\d|2[0-3]):[0-5]\d$/.test(dayEnd) && dayEnd !== '00:00' && numbers.every((n) => Number.isInteger(n) && n >= 0)
  return (
    <form
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) save.mutate({ day_end_time: dayEnd, sample_every: numbers[0], session_ttl_minutes: numbers[1], allow_deferred_auto: deferred })
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rule-day-end">{t('cleaning.rules.dayEnd')}</Label>
        <Input id="rule-day-end" type="time" value={dayEnd} onChange={(e) => setDayEnd(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rule-sample">{t('cleaning.rules.sample')}</Label>
        <Input id="rule-sample" type="number" min={0} value={sample} onChange={(e) => setSample(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rule-ttl">{t('cleaning.rules.ttl')}</Label>
        <Input id="rule-ttl" type="number" min={0} value={ttl} onChange={(e) => setTtl(e.target.value)} />
      </div>
      <label className="flex items-center gap-2 self-end text-[13px] text-text-primary">
        <input type="checkbox" checked={deferred} onChange={(e) => setDeferred(e.target.checked)} />
        {t('cleaning.rules.deferred')}
      </label>
      <div className="flex items-center gap-3 sm:col-span-2 lg:col-span-4">
        <Button type="submit" variant="outline" disabled={!valid || save.isPending}>{t('cleaning.rules.save')}</Button>
        {/* Настройки действуют с завтра, кроме продления конца дня — поэтому показываем
            не обещание, а факт: до какого времени фото принимаются СЕГОДНЯ. */}
        <p className="text-[12px] text-text-muted">
          {rules.today_end_at
            ? t('cleaning.rules.todayUntil', { time: formatTime(rules.today_end_at) })
            : t('cleaning.rules.effective')}
        </p>
      </div>
    </form>
  )
}

const BACKLOG_DAYS = 60
const TIMESHEET_COLS = ['cleaner', 'planned', 'accepted', 'rejected', 'expired', 'missed', 'complaints', 'percent'] as const

/** Табель как data:-ссылка на CSV (BOM и «;» — чтобы Excel открыл кириллицу столбцами). */
function timesheetCsv(head: string[], rows: (string | number)[][]): string {
  const cell = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`
  const text = [head, ...rows].map((row) => row.map(cell).join(';')).join('\r\n')
  return `data:text/csv;charset=utf-8,${encodeURIComponent(`\uFEFF${text}`)}`
}

export default function CleaningControlPage() {
  const { t } = useTranslation()
  usePageTitle(t('cleaning.control.title'))
  const person = usePersonName()
  const today = isoDate(new Date())
  const [weekStart, setWeekStart] = useState(() => mondayOf(today))
  const weekEnd = addDays(weekStart, 6)
  const [monthFrom, monthTo] = monthRange(weekStart)
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))

  const tasks = useCleaningTasks(weekStart, weekEnd)
  // Очередь и жалобы не зависят от просматриваемой недели: вчерашний вопрос не должен пропасть в понедельник.
  const backlogFrom = addDays(today, -BACKLOG_DAYS)
  const backlog = useCleaningTasks(backlogFrom, today, 'review')
  const complaints = useCleaningComplaints(backlogFrom, today)
  const timesheet = useCleaningTimesheet(monthFrom, monthTo)
  const rules = useCleaningRules()
  const decideComplaint = useDecideCleaningComplaint()

  if (tasks.isLoading) return <LoadingSpinner />
  if (tasks.isError || !tasks.data) return <div className="p-6"><p className="text-[13px] text-red">{t('common.error')}</p></div>

  const rows = tasks.data.tasks
  const byCell = new Map<string, CleaningTaskRow>(rows.map((row) => [`${row.building_id}:${row.entrance}:${row.work_date}`, row]))
  const entrances = [...new Map(rows.map((row) => [`${row.building_id}:${row.entrance}`, row])).values()]
  const todays = rows.filter((row) => row.work_date === today)
  const count = (...statuses: CleaningTaskStatus[]) => todays.filter((row) => statuses.includes(row.status)).length
  const queue = (backlog.data?.tasks ?? rows).filter((row) => row.status === 'review')
  const place = (row: { address?: string; building_id: number; entrance: number }) =>
    `${row.address ?? entrances.find((e) => e.building_id === row.building_id)?.address ?? `#${row.building_id}`}, ${t('cleaning.staff.entrance', { n: row.entrance })}`

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[18px] font-semibold text-text-primary">{t('cleaning.control.title')}</h1>
          <p className="text-[13px] text-text-muted">{t('cleaning.control.week', { from: shortDate(weekStart), to: shortDate(weekEnd) })}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => setWeekStart(addDays(weekStart, -7))}>{t('cleaning.control.prevWeek')}</Button>
          <Button type="button" variant="outline" size="sm" onClick={() => setWeekStart(addDays(weekStart, 7))}>{t('cleaning.control.nextWeek')}</Button>
          <Link to="/dashboard/cleaning" className="text-[13px] font-medium text-accent">{t('cleaning.staff.planLink')}</Link>
          <Link to="/dashboard/cleaning/staff" className="text-[13px] font-medium text-accent">{t('cleaning.plan.staffLink')}</Link>
        </div>
      </div>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label={t('cleaning.control.today')}>
        {([
          ['total', todays.length, ''],
          ['accepted', count('accepted'), 'text-green'],
          ['review', count('review'), 'text-amber'],
          ['unfinished', count('planned', 'in_progress', 'missed', 'expired'), 'text-red'],
        ] as const).map(([key, value, tone]) => (
          <div key={key} className={CARD}>
            <p className="text-[12px] text-text-muted">{t(`cleaning.control.summary.${key}`)}</p>
            <p className={cn('text-[26px] font-bold text-text-primary', tone)}>{value}</p>
          </div>
        ))}
      </section>

      <section className={CARD} aria-label={t('cleaning.control.matrix')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.control.matrix')}</h2>
        {entrances.length === 0 && <p className="text-[13px] text-text-muted">{t('cleaning.control.noTasks')}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] text-text-primary">
            <thead>
              <tr className="text-left text-text-muted">
                <th className="p-2 font-medium">{t('cleaning.control.entrance')}</th>
                {days.map((day, i) => <th key={day} className="p-2 font-medium">{t(`cleaning.day.${i}`)} {shortDate(day)}</th>)}
              </tr>
            </thead>
            <tbody>
              {entrances.map((entrance) => (
                <tr key={`${entrance.building_id}:${entrance.entrance}`} className="border-t border-border-default">
                  <td className="p-2 font-semibold whitespace-nowrap">{place(entrance)}</td>
                  {days.map((day) => {
                    const cell = byCell.get(`${entrance.building_id}:${entrance.entrance}:${day}`)
                    return (
                      <td key={day} className="p-2 whitespace-nowrap">
                        {cell ? (
                          <Link to={`/dashboard/cleaning/tasks/${cell.id}`} className={STATUS_CLASS[cell.status]}>
                            {t(`cleaning.status.${cell.status}`)} {cell.slots_done}/{cell.slots_total}
                          </Link>
                        ) : <span className="text-text-muted">—</span>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={CARD} aria-label={t('cleaning.control.queue')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.control.queue')} — {queue.length}</h2>
        {queue.length === 0 && <p className="text-[13px] text-text-muted">{t('cleaning.control.queueEmpty')}</p>}
        <ul className="flex flex-col gap-1.5">
          {queue.map((row) => (
            <li key={row.id} className="list-none text-[13px] text-text-primary">
              <Link to={`/dashboard/cleaning/tasks/${row.id}`} className="font-medium text-accent">
                {shortDate(row.work_date)} · {place(row)}
              </Link>
              {row.sampled && <span className="ml-2 text-text-muted">{t('cleaning.control.sampled')}</span>}
            </li>
          ))}
        </ul>
      </section>

      <section className={CARD} aria-label={t('cleaning.control.complaints')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.control.complaints')}</h2>
        {(complaints.data ?? []).length === 0 && <p className="text-[13px] text-text-muted">{t('cleaning.control.complaintsEmpty')}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] text-text-primary">
            <tbody>
              {(complaints.data ?? []).map((complaint) => (
                <tr key={complaint.id} className="border-t border-border-default">
                  <td className="p-2 whitespace-nowrap">{shortDate(complaint.work_date)}</td>
                  <td className="p-2">{place(complaint)}</td>
                  <td className="p-2">{complaint.request_number ?? t('cleaning.control.noRequest')}</td>
                  <td className="p-2">
                    {complaint.task_id
                      ? <Link to={`/dashboard/cleaning/tasks/${complaint.task_id}`} className="font-medium text-accent">{t('cleaning.control.openTask')}</Link>
                      : t('cleaning.control.noTask')}
                  </td>
                  <td className="p-2 text-right whitespace-nowrap">
                    {complaint.outcome === 'pending' ? (
                      <>
                        <Button type="button" variant="outline" size="sm" disabled={decideComplaint.isPending}
                          onClick={() => decideComplaint.mutate({ id: complaint.id, outcome: 'confirmed' })}>
                          {t('cleaning.complaint.confirm')}
                        </Button>
                        <Button type="button" variant="ghost" size="sm" className="ml-1" disabled={decideComplaint.isPending}
                          onClick={() => decideComplaint.mutate({ id: complaint.id, outcome: 'unfounded' })}>
                          {t('cleaning.complaint.dismiss')}
                        </Button>
                      </>
                    ) : t(`cleaning.complaint.${complaint.outcome}`)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={CARD} aria-label={t('cleaning.control.timesheet')}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[14px] font-semibold text-text-primary">
            {t('cleaning.control.timesheet')} · {shortDate(monthFrom)}–{shortDate(monthTo)}
          </h2>
          <Button asChild variant="outline" size="sm">
            <a
              download={`cleaning-timesheet-${monthFrom}.csv`}
              href={timesheetCsv(
                TIMESHEET_COLS.map((key) => t(`cleaning.timesheet.${key}`)),
                (timesheet.data ?? []).map((row) => [
                  person.full(row, `#${row.user_id}`), row.planned, row.accepted, row.rejected, row.expired, row.missed,
                  `${row.complaints} / ${row.confirmed}`, `${row.percent}%`,
                ]),
              )}
            >
              {t('cleaning.control.export')}
            </a>
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] text-text-primary">
            <thead>
              <tr className="text-left text-text-muted">
                {TIMESHEET_COLS.map((key) => (
                  <th key={key} className="p-2 font-medium">{t(`cleaning.timesheet.${key}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(timesheet.data ?? []).map((row) => (
                <tr key={row.user_id} className="border-t border-border-default">
                  <td className="p-2 font-semibold">{person.full(row, `#${row.user_id}`)}</td>
                  <td className="p-2">{row.planned}</td>
                  <td className="p-2">{row.accepted}</td>
                  <td className="p-2">{row.rejected}</td>
                  <td className="p-2">{row.expired}</td>
                  <td className="p-2">{row.missed}</td>
                  <td className="p-2">{row.complaints} / {row.confirmed}</td>
                  <td className="p-2 font-semibold">{row.percent}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={CARD} aria-label={t('cleaning.rules.title')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.rules.title')}</h2>
        {rules.data && <RulesForm key={rules.data.version ?? 0} rules={rules.data} />}
      </section>
    </div>
  )
}
