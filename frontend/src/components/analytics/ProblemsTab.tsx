import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import EmptyState from '../shared/EmptyState'
import { startProblems, useProblems } from '../../hooks/useAnalytics'
import { apiErrorDetail } from '../../utils/errorMessage'
import { daysInRange, type DateRange } from '../../utils/analyticsPeriod'
import { formatDateTime } from '../../utils/timezone'
import type { LocalizedText, ProblemOut, ProblemSeverity } from '../../types/api'
import { Panel, RequestLink } from './shared'

/** Совпадает с MAX_DAYS сервиса (`services/request_analytics/problems.py`). */
export const PROBLEMS_MAX_DAYS = 92

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

interface Props {
  range: DateRange
}

export default function ProblemsTab({ range }: Props) {
  const { t } = useTranslation()
  const pick = useLocalized()
  const queryClient = useQueryClient()
  const status = useProblems(range)
  const [starting, setStarting] = useState(false)
  const data = status.data
  const tooLong = daysInRange(range) > PROBLEMS_MAX_DAYS
  const running = Boolean(data?.running) || starting
  const busy = Boolean(data?.busy) && !running
  const report = data?.report ?? null

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

  const hint = !data?.available
    ? t('analytics.problems.unavailable')
    : tooLong
      ? t('analytics.problems.tooLong', { days: PROBLEMS_MAX_DAYS })
      : busy
        ? t('analytics.problems.busy')
        : t('analytics.problems.hint')

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={t('analytics.problems.title')}
        actions={
          <Button onClick={run} disabled={running || busy || tooLong || !data?.available}>
            <Sparkles className="size-4" aria-hidden />
            {running
              ? t('analytics.problems.running')
              : report ? t('analytics.problems.rerun') : t('analytics.problems.run')}
          </Button>
        }
      >
        <p className="text-[13px] text-text-muted">{running ? t('analytics.problems.runningHint') : hint}</p>
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
