import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import ConfirmDialog from '../components/shared/ConfirmDialog'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import GroupSection from '../components/workReports/GroupSection'
import ReasonDialog, { type ReasonTarget } from '../components/workReports/ReasonDialog'
import WorkReportRow from '../components/workReports/WorkReportRow'
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
import { WORK_REPORT_CATEGORY_KEYS, type WorkReport } from '../types/workReports'
import type { WorkReportsCfg } from '../types/boardConfig'

/**
 * T11 — менеджерская очередь модерации визуальных отчётов «до/после»
 * (work-reports). Изолированный компонент страницы: маршрут (App.tsx) и
 * пункт меню (DashboardLayout.tsx) подключает следующая задача.
 *
 * Read-модель настроек — НЕ отдельный эндпоинт (его нет), а
 * useBoardConfig().data?.work_reports, см. заголовок useWorkReports.ts.
 *
 * Подкомпоненты (GroupSection/ReasonDialog/WorkReportRow) вынесены в
 * components/workReports/* — по прецеденту EmployeesPage.tsx
 * (components/employees/*) и ResolveDialog.tsx (components/access/*), а не
 * инлайнены в файл страницы.
 */

const DEFAULT_SETTINGS: WorkReportsCfg = {
  autopost: false,
  autopost_since: null,
  autopublish: false,
  categories: [],
  limit: 6,
  title: { ru: '', uz: '' },
}

export default function WorkReportsPage() {
  const { t } = useTranslation()
  usePageTitle(t('workReports.title'))

  const { data: boardConfig } = useBoardConfig()
  const rawSettings = boardConfig?.work_reports
  // Нормализуем, а не берём блок как есть: фронт может доехать раньше бэкенда
  // (или ответить из кэша старой версии), и тогда `categories`/`autopublish` в
  // ответе отсутствуют. Без этого `settings.categories.includes(...)` падал бы
  // и уносил всю страницу, а не одну настройку.
  //
  // useMemo обязателен, а не косметика: ссылка на `settings` участвует в
  // reseed-проверке ниже (`settings !== seededFrom`), и новый объект на каждом
  // рендере зациклил бы setState.
  const settings: WorkReportsCfg = useMemo(
    () => ({
      ...DEFAULT_SETTINGS,
      ...(rawSettings ?? {}),
      categories: rawSettings?.categories ?? [],
    }),
    [rawSettings],
  )

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

  // 'publishing' folds into the moderation group rather than getting its own
  // section: it's a transient in-flight state that should barely ever be
  // observed and has no actions of its own (WorkReportRow renders it as a
  // plain "публикуется…" label, no buttons).
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

        {/* Публикация без модерации. Отдельным блоком с явным предупреждением,
            а не ещё одним чекбоксом в ряд с лимитом: это единственная
            настройка, которая убирает человека из цепочки перед публикацией
            фотографий. Мутация уходит сразу, как у тумблера автопостинга. */}
        <div className="border-t border-border-default pt-4 flex flex-col gap-2">
          <label className="flex items-start gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={settings.autopublish}
              onChange={() => updateSettings.mutate({ autopublish: !settings.autopublish })}
              disabled={updateSettings.isPending}
              aria-label={t('workReports.settings.autopublishLabel')}
            />
            <span className="flex flex-col gap-0.5">
              <span
                className={
                  settings.autopublish
                    ? 'text-[13px] font-semibold text-amber-600 dark:text-amber-400'
                    : 'text-[13px] font-semibold text-text-primary'
                }
              >
                {t('workReports.settings.autopublishLabel')}
              </span>
              <span className="text-[12px] text-text-muted">
                {t('workReports.settings.autopublishHint')}
              </span>
            </span>
          </label>
        </div>

        {/* Фильтр категорий: что вообще попадает в ленту. Ни одной галки =
            без ограничения (пустой фильтр ничего не отсекает) — подписано
            явно, иначе пустое состояние читается как «ничего не публикуется». */}
        <div className="border-t border-border-default pt-4 flex flex-col gap-2">
          <span className="text-[13px] font-semibold text-text-primary">
            {t('workReports.settings.categoriesLabel')}
          </span>
          <span className="text-[12px] text-text-muted">
            {settings.categories.length === 0
              ? t('workReports.settings.categoriesAll')
              : t('workReports.settings.categoriesHint')}
          </span>
          <div className="flex flex-wrap gap-x-4 gap-y-2 pt-1">
            {WORK_REPORT_CATEGORY_KEYS.map((key) => (
              <label key={key} className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.categories.includes(key)}
                  disabled={updateSettings.isPending}
                  onChange={() =>
                    updateSettings.mutate({
                      categories: settings.categories.includes(key)
                        ? settings.categories.filter((c) => c !== key)
                        : [...settings.categories, key],
                    })
                  }
                />
                {tCategory(key, t)}
              </label>
            ))}
          </div>
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
