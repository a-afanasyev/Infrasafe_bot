import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import EmptyState from '../shared/EmptyState'
import { startProblems, useProblems } from '../../hooks/useAnalytics'
import { apiErrorDetail } from '../../utils/errorMessage'
import { daysInRange, type DateRange } from '../../utils/analyticsPeriod'
import { useCan } from '../../hooks/useCan'
import { formatDate, formatDateTime } from '../../utils/timezone'
import type { LocalizedText, ProblemOut, ProblemSeverity, RecentProblemsOut } from '../../types/api'
import { Panel, RequestLink } from './shared'

/** Совпадает с MAX_DAYS сервиса (`services/request_analytics/problems.py`). */
export const PROBLEMS_MAX_DAYS = 92
/** Предел setTimeout (~24.8 сут.); ограничение суток короче. */
const MAX_TIMEOUT_MS = 2 ** 31 - 1

const SEVERITY_COLOR: Record<ProblemSeverity, string> = {
  critical: 'var(--red)',
  high: 'var(--orange)',
  medium: 'var(--amber)',
}

function useLocalized() {
  const { i18n } = useTranslation()
  const uz = i18n.language.startsWith('uz')
  return (text: LocalizedText) => (uz ? text.uz : text.ru)
}

function ProblemCard({ index, problem }: { index: number; problem: ProblemOut }) {
  const { t } = useTranslation()
  const pick = useLocalized()
  const color = SEVERITY_COLOR[problem.severity]
  return (
    <article className="rounded-default bg-bg-card border border-border-default p-4 min-w-0 flex flex-col gap-2">
      <div className="flex items-start gap-3">
        <span className="font-[family-name:var(--font-mono)] text-lg font-bold leading-none text-text-muted">
          {index}
        </span>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm text-text-primary break-words">{pick(problem.title)}</h3>
          <div className="flex flex-wrap gap-2 mt-1 text-[11px]">
            <span
              className="px-2 py-0.5 rounded-sm font-semibold"
              style={{ color, background: `color-mix(in srgb, ${color} 12%, transparent)` }}
            >
              {t(`analytics.problems.severity.${problem.severity}`)}
            </span>
            <span className="px-2 py-0.5 rounded-sm bg-bg-surface text-text-secondary">
              {t(`analytics.problems.area.${problem.area}`)}
            </span>
          </div>
        </div>
      </div>
      <p className="text-[13px] text-text-secondary whitespace-pre-line break-words">{pick(problem.description)}</p>
      <p className="text-[13px] text-text-primary break-words">
        <span className="font-semibold">{t('analytics.problems.recommendation')}: </span>
        {pick(problem.recommendation)}
      </p>
      <div className="flex flex-wrap gap-x-2 gap-y-1 text-[12px]">
        <span className="text-text-muted">{t('analytics.problems.evidence')}:</span>
        {problem.evidence.map(n => <RequestLink key={n} number={n} />)}
      </div>
    </article>
  )
}

/** Последние разборы других периодов: открыть готовое вместо нового платного запуска. */
function RecentReports({ items, range, onPick }: {
  items: RecentProblemsOut[]
  range: DateRange
  onPick: (range: DateRange) => void
}) {
  const { t } = useTranslation()
  const others = items.filter(r => r.first !== range.from || r.last !== range.to)
  if (others.length === 0) return null
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px]">
      <span className="text-text-muted">{t('analytics.problems.recent')}:</span>
      {others.map(r => (
        <button
          key={`${r.first}-${r.last}`}
          type="button"
          onClick={() => onPick({ from: r.first, to: r.last })}
          className="px-2 py-0.5 rounded-sm border border-border-default bg-bg-surface text-text-secondary hover:border-border-active hover:text-text-primary cursor-pointer"
          title={r.generated_at ? formatDateTime(r.generated_at) : undefined}
        >
          {formatDate(r.first)} — {formatDate(r.last)}
        </button>
      ))}
    </div>
  )
}

interface Props {
  range: DateRange
  /** Открыть готовый разбор другого периода (переключает период страницы). */
  onPickRange: (range: DateRange) => void
}

export default function ProblemsTab({ range, onPickRange }: Props) {
  const { t } = useTranslation()
  const pick = useLocalized()
  const queryClient = useQueryClient()
  const canRun = useCan('requests.problems')
  const status = useProblems(range)
  const [starting, setStarting] = useState(false)
  const data = status.data
  const tooLong = daysInRange(range) > PROBLEMS_MAX_DAYS
  const running = Boolean(data?.running) || starting
  const busy = Boolean(data?.busy) && !running
  const waitUntil = data?.next_run_at && new Date(data.next_run_at).getTime() > Date.now()
    ? data.next_run_at : null
  const report = data?.report ?? null

  // Ограничение кончилось — перезапросить статус ровно в этот момент: кнопка
  // оживает сама (опрос без конца бил бы сервер у всех, кто держит вкладку).
  const { refetch } = status
  const nextRunAt = data?.next_run_at ?? null
  useEffect(() => {
    if (!canRun || !nextRunAt) return
    const ms = new Date(nextRunAt).getTime() - Date.now()
    if (ms <= 0) return
    const id = setTimeout(() => { void refetch() }, Math.min(ms + 1000, MAX_TIMEOUT_MS))
    return () => clearTimeout(id)
  }, [canRun, nextRunAt, refetch])

  const run = async () => {
    setStarting(true)
    try {
      await startProblems(range)
    } catch (error: unknown) {
      toast.error(apiErrorDetail(error) ?? t('analytics.problems.startFailed'))
    } finally {
      await queryClient.invalidateQueries({ queryKey: ['request-stats', '/problems'] })
      setStarting(false)
    }
  }

  const hint = !canRun
    ? t('analytics.problems.viewOnly')
    : !data?.available
      ? t('analytics.problems.unavailable')
      : tooLong
        ? t('analytics.problems.tooLong', { days: PROBLEMS_MAX_DAYS })
        : busy
          ? t('analytics.problems.busy')
          : waitUntil
            ? t('analytics.problems.waitUntil', { time: formatDateTime(waitUntil) })
            : t('analytics.problems.hint')

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={t('analytics.problems.title')}
        actions={canRun && (
          <Button onClick={run} disabled={running || busy || tooLong || Boolean(waitUntil) || !data?.available}>
            <Sparkles className="size-4" aria-hidden />
            {running
              ? t('analytics.problems.running')
              : report ? t('analytics.problems.rerun') : t('analytics.problems.run')}
          </Button>
        )}
      >
        <p className="text-[13px] text-text-muted">{running ? t('analytics.problems.runningHint') : hint}</p>
        {canRun && data?.available && data.runs_left !== null && !running && (
          <p className="mt-1 text-[12px] text-text-muted">
            {t('analytics.problems.runsLeft', { count: data.runs_left })}
          </p>
        )}
        <RecentReports items={data?.recent ?? []} range={range} onPick={onPickRange} />
        {data?.failed && !running && (
          <div className="mt-3 p-3 px-4 rounded-sm bg-red/10 border border-red/30 text-red text-[13px]">
            {t('analytics.problems.failed')}
          </div>
        )}
      </Panel>

      {report ? (
        <>
          <Panel title={t('analytics.problems.summary')}>
            <p className="text-[13px] text-text-primary whitespace-pre-line break-words">{pick(report.summary)}</p>
            <p className="mt-2 text-[12px] text-text-muted">
              {t('analytics.problems.meta', {
                date: formatDateTime(report.generated_at),
                count: report.request_count,
              })}
              {report.truncated && ` ${t('analytics.problems.truncated')}`}
            </p>
          </Panel>
          {report.problems.length === 0 ? (
            <EmptyState icon={'\u{2705}'} title={t('analytics.problems.none')} />
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              {report.problems.map((p, i) => <ProblemCard key={`${i}-${p.title.ru}`} index={i + 1} problem={p} />)}
            </div>
          )}
        </>
      ) : (
        !running && data && <EmptyState icon={'\u{1F50E}'} title={t('analytics.problems.empty')} />
      )}
    </div>
  )
}
