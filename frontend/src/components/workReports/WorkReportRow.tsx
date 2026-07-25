import type { TFunction } from 'i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { tCategory } from '../../i18n/apiMaps'
import { formatDate } from '../../utils/timezone'
import type { WorkReport, WorkReportStatus } from '../../types/workReports'

const STATUS_CLASS: Record<WorkReportStatus, string> = {
  pending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  needs_media: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  publishing: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  published: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  needs_review: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  rejected: 'bg-gray-100 text-gray-700 dark:bg-gray-800/40 dark:text-gray-300',
}

// publish/autofill are single mutation instances shared across every row in
// the group (one useMutation() call per action on the page, reused per row)
// — `.variables` (the id most recently passed to `.mutate()`) is what lets a
// row tell "an action is in flight, and it's MINE" apart from "an action is
// in flight somewhere in this group". Structural subset of
// UseMutationResult<..., number> — real hook objects satisfy this.
interface MutationLike {
  mutate: (id: number) => void
  isPending: boolean
  variables?: number
}

/**
 * One report row: status chip, category, address, date, and per-status
 * actions (PendingApprovalCard.tsx `disabled={...isPending}` convention).
 */
export default function WorkReportRow({
  report,
  t,
  publish,
  autofill,
  onReject,
  onUnpublish,
  onReopen,
}: {
  report: WorkReport
  t: TFunction
  publish: MutationLike
  autofill: MutationLike
  onReject: (report: WorkReport) => void
  onUnpublish: (report: WorkReport) => void
  onReopen: (report: WorkReport) => void
}) {
  const isNeedsMedia = report.status === 'needs_media'
  const isModerationStage = report.status === 'pending' || report.status === 'needs_media'
  // Scoped per-row: only THIS row's in-flight mutation disables THIS row's
  // button — a shared mutation instance's `.isPending` alone would grey out
  // every row in the group while any one of them is in flight.
  const publishPendingHere = publish.isPending && publish.variables === report.id
  const autofillPendingHere = autofill.isPending && autofill.variables === report.id

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-default border border-border-default bg-bg-card px-4 py-3">
      <div className="flex-1 min-w-[220px]">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn('px-2 py-0.5 rounded-full text-[11px] font-medium', STATUS_CLASS[report.status])}>
            {t(`workReports.status.${report.status}`)}
          </span>
          <span className="text-[13px] font-semibold text-text-primary">{tCategory(report.category_key, t)}</span>
          <span className="font-mono text-[12px] text-text-muted">{report.request_number}</span>
        </div>
        <div className="mt-0.5 text-[12px] text-text-muted">
          {report.address_public} · {formatDate(report.performed_at)}
        </div>
        {report.status === 'needs_review' && report.reject_reason && (
          <div className="mt-1 text-[12px] text-red-600 dark:text-red-400">{report.reject_reason}</div>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {report.status === 'publishing' && (
          <span className="text-[12px] text-text-muted italic">{t('workReports.status.publishing')}…</span>
        )}

        {isModerationStage && (
          <>
            {isNeedsMedia && (
              <span className="text-[11px] text-amber-700 dark:text-amber-300">
                {t('workReports.needsMediaExplanation')}
              </span>
            )}
            <Button size="sm" disabled={isNeedsMedia || publishPendingHere} onClick={() => publish.mutate(report.id)}>
              {t('workReports.actions.publish')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={autofillPendingHere}
              onClick={() => autofill.mutate(report.id)}
            >
              {t('workReports.actions.autofill')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="border-red text-red hover:bg-red/10"
              onClick={() => onReject(report)}
            >
              {t('workReports.actions.reject')}
            </Button>
          </>
        )}

        {(report.status === 'published' || report.status === 'needs_review') && (
          <Button size="sm" variant="outline" onClick={() => onUnpublish(report)}>
            {t('workReports.actions.unpublish')}
          </Button>
        )}

        {report.status === 'rejected' && (
          <Button size="sm" variant="outline" onClick={() => onReopen(report)}>
            {t('workReports.actions.reopen')}
          </Button>
        )}
      </div>
    </div>
  )
}
