import { useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { usePageTitle } from '../../hooks/usePageTitle'
import { useElevatorsConfig, useSaveElevatorsConfig } from '../../hooks/useElevatorsConfig'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import FormSection from '../../components/elevators/FormSection'
import {
  configDraftFrom,
  configDraftToPayload,
  isValidStages,
  type ElevatorsConfigDraft,
} from '../../utils/elevatorsConfigForm'

/**
 * Настройки модуля (/dashboard/elevators/config, manager): пороги простоя
 * (пусто = «не напоминать» → null), тумблеры уведомлений жителям, стадии
 * напоминаний персоналу (списки дней), overdue_weekly, module_public
 * (публичный виджет на табло жителей, T16), запрет заявок жителей по лифту в
 * работах (Р18a, выключен = запрет действует). Черновик сидится из GET один раз
 * и пересиживается из ответа PUT (паттерн AutoManagerCard).
 */
type Draft = ElevatorsConfigDraft

function Toggle({ id, label, checked, onChange, disabled = false, hint }: {
  id: string; label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; hint?: string
}) {
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-[13px] text-text-primary" title={hint}>
      <input id={id} type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {label}
      {hint && <span className="text-text-muted">— {hint}</span>}
    </label>
  )
}

export default function ElevatorsConfigPage() {
  const { t } = useTranslation()
  usePageTitle(t('elevators.config.title'))
  const config = useElevatorsConfig()
  const save = useSaveElevatorsConfig()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Сид один раз: фоновые рефетчи не затирают несохранённый ввод.
  if (config.data && draft === null) setDraft(configDraftFrom(config.data))

  if (config.isLoading || (!draft && !config.isError)) return <LoadingSpinner />
  if (config.isError || !draft || !config.data) {
    return <div className="p-6"><p className="text-[13px] text-red">{t('common.error')}</p></div>
  }

  const patch = (p: Partial<Draft>) => setDraft((prev) => (prev ? { ...prev, ...p } : prev))

  const submit = () => {
    const listsOk = [draft.maintenance, draft.certification, draft.contract].every(isValidStages)
    if (!listsOk) {
      setError(t('elevators.config.invalidStages'))
      return
    }
    setError(null)
    save.mutate(configDraftToPayload(draft), { onSuccess: (saved) => setDraft(configDraftFrom(saved)) })
  }

  const numberField = (id: keyof Pick<Draft, 'not_working' | 'under_repair'>, labelKey: string) => (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={`cfg-${id}`}>{t(labelKey)}</Label>
      <Input
        id={`cfg-${id}`} type="number" min={1} value={draft[id]}
        placeholder={t('elevators.config.noRemind')}
        onChange={(e) => patch({ [id]: e.target.value } as Partial<Draft>)}
      />
    </div>
  )

  const listField = (id: keyof Pick<Draft, 'maintenance' | 'certification' | 'contract'>, labelKey: string) => (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={`cfg-${id}`}>{t(labelKey)}</Label>
      <Input
        id={`cfg-${id}`} value={draft[id]} placeholder={t('elevators.config.stagesHint')}
        onChange={(e) => patch({ [id]: e.target.value } as Partial<Draft>)}
      />
    </div>
  )

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <Button asChild variant="outline" size="sm">
          <Link to="/dashboard/elevators" aria-label={t('elevators.actions.backToList')}><ArrowLeft size={15} /></Link>
        </Button>
        <Settings className="text-accent" size={22} />
        <div>
          <h1 className="text-xl font-semibold text-text-primary">{t('elevators.config.title')}</h1>
          <p className="text-[13px] text-text-muted">{t('elevators.config.subtitle')}</p>
        </div>
      </div>

      <FormSection title={t('elevators.config.thresholds')}>
        {numberField('not_working', 'elevators.config.notWorkingDays')}
        {numberField('under_repair', 'elevators.config.underRepairDays')}
      </FormSection>

      <FormSection title={t('elevators.config.residentNotifications')} grid={false}>
        <Toggle id="cfg-repair_started" label={t('elevators.config.repairStarted')} checked={draft.repair_started} onChange={(v) => patch({ repair_started: v })} />
        <Toggle id="cfg-maintenance_started" label={t('elevators.config.maintenanceStarted')} checked={draft.maintenance_started} onChange={(v) => patch({ maintenance_started: v })} />
        <Toggle id="cfg-back_in_service" label={t('elevators.config.backInService')} checked={draft.back_in_service} onChange={(v) => patch({ back_in_service: v })} />
      </FormSection>

      <FormSection title={t('elevators.config.staffReminders')}>
        {listField('maintenance', 'elevators.config.maintenance')}
        {listField('certification', 'elevators.config.certification')}
        {listField('contract', 'elevators.config.contract')}
        <Toggle id="cfg-overdue_weekly" label={t('elevators.config.overdueWeekly')} checked={draft.overdue_weekly} onChange={(v) => patch({ overdue_weekly: v })} />
      </FormSection>

      <FormSection title={t('elevators.config.residentRequests')} grid={false}>
        <Toggle
          id="cfg-allow_resident_requests_under_works"
          label={t('elevators.config.allowUnderWorks')}
          checked={draft.allow_resident_requests_under_works}
          onChange={(v) => patch({ allow_resident_requests_under_works: v })}
          hint={t('elevators.config.allowUnderWorksHint')}
        />
      </FormSection>

      <FormSection title={t('elevators.config.modulePublic')} grid={false}>
        <Toggle
          id="cfg-module_public" label={t('elevators.config.modulePublic')} checked={draft.module_public}
          onChange={(v) => patch({ module_public: v })} hint={t('elevators.config.modulePublicHint')}
        />
      </FormSection>

      {error && <p role="alert" className="text-[13px] text-red">{error}</p>}

      <div>
        <Button onClick={submit} disabled={save.isPending}>
          {save.isPending ? t('common.saving') : t('common.save')}
        </Button>
      </div>
    </div>
  )
}
