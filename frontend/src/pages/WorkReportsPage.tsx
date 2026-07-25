import { useState, type ReactNode } from 'react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import ConfirmDialog from '../components/shared/ConfirmDialog'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { usePageTitle } from '../hooks/usePageTitle'
import { useBoardConfig } from '../hooks/useBoardConfig'
import {
  useWorkReports,
  useSyncWorkReports,
  useCreateWorkReport,
  useAutofillWorkReport,
  usePublishWorkReport,
  useUnpublishWorkReport,
  useRejectWorkReport,
  useReopenWorkReport,
  useUpdateWorkReportsSettings,
} from '../hooks/useWorkReports'
import { tCategory } from '../i18n/apiMaps'
import { formatDate } from '../utils/timezone'
import type { WorkReport, WorkReportStatus } from '../types/workReports'
import type { WorkReportsCfg } from '../types/boardConfig'

/**
 * T11 — менеджерская очередь модерации визуальных отчётов «до/после»
 * (work-reports). Изолированный компонент страницы: маршрут (App.tsx) и
 * пункт меню (DashboardLayout.tsx) подключает следующая задача.
 *
 * Read-модель настроек — НЕ отдельный эндпоинт (его нет), а
 * useBoardConfig().data?.work_reports, см. заголовок useWorkReports.ts.
 */

const DEFAULT_SETTINGS: WorkReportsCfg = {
  autopost: false,
  autopost_since: null,
  limit: 6,
  title: { ru: '', uz: '' },
}

const STATUS_CLASS: Record<WorkReportStatus, string> = {
  pending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  needs_media: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  publishing: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  published: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  needs_review: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  rejected: 'bg-gray-100 text-gray-700 dark:bg-gray-800/40 dark:text-gray-300',
}

// ── Section wrapper (EmployeesPage.tsx pending-block shape): heading + count
// badge, hidden entirely when the group is empty. ──────────────────────────
function GroupSection({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  if (count === 0) return null
  return (
    <div className="bg-bg-card border border-border-default rounded-default p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="font-[var(--font-display)] font-semibold text-sm text-text-primary">{title}</span>
        <span className="bg-amber/20 text-amber rounded-full px-2 py-0.5 text-[11px] font-semibold">{count}</span>
      </div>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  )
}

// ── Reject/unpublish reason dialog (ResolveDialog.tsx shape, ported to the
// workReports.* i18n namespace — reject requires a non-empty reason,
// unpublish does not). ──────────────────────────────────────────────────────
interface ReasonTarget {
  report: WorkReport
  action: 'reject' | 'unpublish'
}

function ReasonDialog({
  target,
  loading,
  onClose,
  onSubmit,
}: {
  target: ReasonTarget | null
  loading?: boolean
  onClose: () => void
  onSubmit: (reason: string) => void
}) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')

  // Сброс поля при смене target — render-time pattern (см. ResolveDialog.tsx):
  // setState-в-effect ругается линтером, а без сброса текст «перетекал» бы
  // между отчётами.
  const [prevTarget, setPrevTarget] = useState<ReasonTarget | null>(null)
  if (target !== prevTarget) {
    setPrevTarget(target)
    if (target) setReason('')
  }

  const isOpen = target !== null
  const isReject = target?.action === 'reject'
  const canSubmit = (!isReject || reason.trim().length > 0) && !loading

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isReject ? t('workReports.actions.reject') : t('workReports.actions.unpublish')}
          </DialogTitle>
          <DialogDescription>{t('workReports.reasonDialogDesc')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="wr-reason">{t('workReports.reasonPlaceholder')}</Label>
          <Textarea
            id="wr-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t('workReports.reasonPlaceholder')}
            rows={3}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={isReject ? 'destructive' : 'default'}
            disabled={!canSubmit}
            onClick={() => onSubmit(reason.trim())}
          >
            {isReject ? t('workReports.actions.reject') : t('workReports.actions.unpublish')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── One report row: status chip, category, address, date, and per-status
// actions (PendingApprovalCard.tsx `disabled={...isPending}` convention). ──
function WorkReportRow({
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
  publish: { mutate: (id: number) => void; isPending: boolean }
  autofill: { mutate: (id: number) => void; isPending: boolean }
  onReject: (report: WorkReport) => void
  onUnpublish: (report: WorkReport) => void
  onReopen: (report: WorkReport) => void
}) {
  const isNeedsMedia = report.status === 'needs_media'
  const isModerationStage = report.status === 'pending' || report.status === 'needs_media'

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
            <Button size="sm" disabled={isNeedsMedia || publish.isPending} onClick={() => publish.mutate(report.id)}>
              {t('workReports.actions.publish')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={autofill.isPending}
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

export default function WorkReportsPage() {
  const { t } = useTranslation()
  usePageTitle(t('workReports.title'))

  const { data: boardConfig } = useBoardConfig()
  const settings = boardConfig?.work_reports ?? DEFAULT_SETTINGS

  const { data: listData, isLoading: listLoading, isError: listError } = useWorkReports()
  const reports = listData?.items ?? []

  const syncReports = useSyncWorkReports()
  const createReport = useCreateWorkReport()
  const autofillReport = useAutofillWorkReport()
  const publishReport = usePublishWorkReport()
  const unpublishReport = useUnpublishWorkReport()
  const rejectReport = useRejectWorkReport()
  const reopenReport = useReopenWorkReport()
  const updateSettings = useUpdateWorkReportsSettings()

  // Настройки лимита/заголовка — черновик с явным "Сохранить" (autopost шлёт
  // мутацию сразу же, см. AutoManagerCard.tsx). Ресид только пока черновик не
  // разошёлся с последним просиженным значением, чтобы не затирать
  // несохранённую правку при фоновом рефетче board-config.
  const [seededFrom, setSeededFrom] = useState<WorkReportsCfg | null>(null)
  const [draftLimit, setDraftLimit] = useState(String(DEFAULT_SETTINGS.limit))
  const [draftTitleRu, setDraftTitleRu] = useState('')
  const [draftTitleUz, setDraftTitleUz] = useState('')

  if (settings !== seededFrom) {
    const untouched =
      seededFrom === null ||
      (draftLimit === String(seededFrom.limit) &&
        draftTitleRu === seededFrom.title.ru &&
        draftTitleUz === seededFrom.title.uz)
    setSeededFrom(settings)
    if (untouched) {
      setDraftLimit(String(settings.limit))
      setDraftTitleRu(settings.title.ru)
      setDraftTitleUz(settings.title.uz)
    }
  }

  const settingsDirty =
    draftLimit !== String(settings.limit) ||
    draftTitleRu !== settings.title.ru ||
    draftTitleUz !== settings.title.uz

  const handleSaveSettings = () => {
    const limitNum = Number(draftLimit)
    if (!Number.isFinite(limitNum) || limitNum < 1 || limitNum > 24) return
    // autopost НЕ включаем сюда — тумблер уже шлёт его отдельной мутацией,
    // а PUT /settings делает partial update (см. useWorkReports.ts).
    updateSettings.mutate({ limit: limitNum, title: { ru: draftTitleRu, uz: draftTitleUz } })
  }

  const [requestNumberInput, setRequestNumberInput] = useState('')
  const handleCreateDraft = () => {
    const requestNumber = requestNumberInput.trim()
    if (!requestNumber) return
    createReport.mutate({ request_number: requestNumber }, { onSuccess: () => setRequestNumberInput('') })
  }

  const [reasonTarget, setReasonTarget] = useState<ReasonTarget | null>(null)
  const [reopenTarget, setReopenTarget] = useState<WorkReport | null>(null)

  const handleReasonSubmit = (reason: string) => {
    if (!reasonTarget) return
    const { report, action } = reasonTarget
    if (action === 'reject') {
      rejectReport.mutate({ id: report.id, reason }, { onSuccess: () => setReasonTarget(null) })
    } else {
      unpublishReport.mutate({ id: report.id, reason }, { onSuccess: () => setReasonTarget(null) })
    }
  }

  const moderationGroup = reports.filter(
    (r) => r.status === 'pending' || r.status === 'needs_media' || r.status === 'publishing',
  )
  const publishedGroup = reports.filter((r) => r.status === 'published')
  const needsReviewGroup = reports.filter((r) => r.status === 'needs_review')
  const rejectedGroup = reports.filter((r) => r.status === 'rejected')

  function renderRow(report: WorkReport) {
    return (
      <WorkReportRow
        key={report.id}
        report={report}
        t={t}
        publish={publishReport}
        autofill={autofillReport}
        onReject={(r) => setReasonTarget({ report: r, action: 'reject' })}
        onUnpublish={(r) => setReasonTarget({ report: r, action: 'unpublish' })}
        onReopen={(r) => setReopenTarget(r)}
      />
    )
  }

  return (
    <div className="p-5 px-6 flex flex-col gap-5">
      {/* Предупреждение о приватности — видно всегда, не завязано на действие. */}
      <div className="flex items-start gap-2.5 rounded-default border border-amber-300/60 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-900/10 px-4 py-3">
        <AlertTriangle size={18} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <span className="text-[13px] text-amber-800 dark:text-amber-200">{t('workReports.privacyWarning')}</span>
      </div>

      {/* Настройки витрины. */}
      <div className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <span className="font-[var(--font-display)] font-semibold text-sm text-text-primary">
            {t('workReports.settings.heading')}
          </span>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-text-muted cursor-pointer">
              <span className={settings.autopost ? 'text-emerald font-semibold' : 'text-text-muted'}>
                {settings.autopost ? t('workReports.settings.autopostOn') : t('workReports.settings.autopostOff')}
              </span>
              <input
                type="checkbox"
                checked={settings.autopost}
                onChange={() => updateSettings.mutate({ autopost: !settings.autopost })}
                disabled={updateSettings.isPending}
                aria-label={t('workReports.settings.toggleLabel')}
              />
            </label>
            <Button size="sm" variant="outline" disabled={syncReports.isPending} onClick={() => syncReports.mutate()}>
              {t('workReports.sync')}
            </Button>
          </div>
        </div>

        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="wr-limit">{t('workReports.settings.limitLabel')}</Label>
            <Input
              id="wr-limit"
              type="number"
              min={1}
              max={24}
              className="w-24"
              value={draftLimit}
              onChange={(e) => setDraftLimit(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="wr-title-ru">{t('workReports.settings.titleLabel')} (RU)</Label>
            <Input
              id="wr-title-ru"
              className="w-64"
              value={draftTitleRu}
              onChange={(e) => setDraftTitleRu(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="wr-title-uz">{t('workReports.settings.titleLabel')} (UZ)</Label>
            <Input
              id="wr-title-uz"
              className="w-64"
              value={draftTitleUz}
              onChange={(e) => setDraftTitleUz(e.target.value)}
            />
          </div>
          <Button size="sm" disabled={!settingsDirty || updateSettings.isPending} onClick={handleSaveSettings}>
            {t('workReports.settings.save')}
          </Button>
        </div>
      </div>

      {/* Ручное создание черновика — только request_number, без override'а
          legacy-адреса (см. описание задачи T11: если бэк вернёт 422, тост
          из useCreateWorkReport уже покажет ошибку). */}
      <div className="bg-bg-card border border-border-default rounded-default p-4 flex items-center gap-2 flex-wrap">
        <Label htmlFor="wr-create-number" className="text-[12px] text-text-muted shrink-0">
          {t('workReports.createDraft.label')}
        </Label>
        <Input
          id="wr-create-number"
          className="w-48"
          value={requestNumberInput}
          onChange={(e) => setRequestNumberInput(e.target.value)}
          placeholder={t('workReports.createDraft.placeholder')}
        />
        <Button size="sm" disabled={!requestNumberInput.trim() || createReport.isPending} onClick={handleCreateDraft}>
          {t('workReports.createDraft.submit')}
        </Button>
      </div>

      {/* Группы по статусам. */}
      {listLoading ? (
        <LoadingSpinner />
      ) : listError ? (
        <p className="text-[13px] text-red px-1">{t('common.error')}</p>
      ) : (
        <>
          <GroupSection title={t('workReports.groups.moderation')} count={moderationGroup.length}>
            {moderationGroup.map(renderRow)}
          </GroupSection>
          <GroupSection title={t('workReports.groups.published')} count={publishedGroup.length}>
            {publishedGroup.map(renderRow)}
          </GroupSection>
          <GroupSection title={t('workReports.groups.needsReview')} count={needsReviewGroup.length}>
            {needsReviewGroup.map(renderRow)}
          </GroupSection>
          <GroupSection title={t('workReports.groups.rejected')} count={rejectedGroup.length}>
            {rejectedGroup.map(renderRow)}
          </GroupSection>
        </>
      )}

      <ReasonDialog
        target={reasonTarget}
        loading={reasonTarget?.action === 'reject' ? rejectReport.isPending : unpublishReport.isPending}
        onClose={() => setReasonTarget(null)}
        onSubmit={handleReasonSubmit}
      />

      <ConfirmDialog
        open={reopenTarget !== null}
        onOpenChange={(open) => !open && setReopenTarget(null)}
        title={t('workReports.actions.reopen')}
        description={reopenTarget ? t('workReports.confirmReopenDesc', { number: reopenTarget.request_number }) : ''}
        confirmLabel={t('workReports.actions.reopen')}
        variant="default"
        loading={reopenReport.isPending}
        onConfirm={() => {
          if (reopenTarget) reopenReport.mutate(reopenTarget.id)
        }}
      />
    </div>
  )
}
