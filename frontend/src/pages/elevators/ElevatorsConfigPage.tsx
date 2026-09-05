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
import { parseIntList, toIntOrNull } from '../../utils/elevatorsFormat'
import type { ElevatorsConfigIn, ElevatorsConfigOut } from '../../types/elevators'

/**
 * Настройки модуля (/dashboard/elevators/config, manager): пороги простоя
 * (пусто = «не напоминать»), тумблеры уведомлений жителям, стадии напоминаний
 * персоналу (списки дней), overdue_weekly, module_public (disabled — второй релиз).
 * Черновик сидится из GET один раз (паттерн AutoManagerCard).
 */
interface Draft {
  not_working: string
  under_repair: string
  repair_started: boolean
  maintenance_started: boolean
  back_in_service: boolean
  maintenance: string
  certification: string
  contract: string
  overdue_weekly: boolean
}

const listToStr = (xs: number[]) => xs.join(', ')

function draftFrom(c: ElevatorsConfigOut): Draft {
  return {
    not_working: c.downtime_threshold_days.not_working?.toString() ?? '',
    under_repair: c.downtime_threshold_days.under_repair?.toString() ?? '',
    repair_started: c.resident_notifications.repair_started,
    maintenance_started: c.resident_notifications.maintenance_started,
    back_in_service: c.resident_notifications.back_in_service,
    maintenance: listToStr(c.staff_reminders.maintenance),
    certification: listToStr(c.staff_reminders.certification),
    contract: listToStr(c.staff_reminders.contract),
    overdue_weekly: c.staff_reminders.overdue_weekly,
  }
}

const INT_LIST_RE = /^\s*(\d+\s*([,;\s]\s*\d+\s*)*)?$/

function toPayload(d: Draft): ElevatorsConfigIn {
  return {
    downtime_threshold_days: {
      not_working: toIntOrNull(d.not_working),
      under_repair: toIntOrNull(d.under_repair),
    },
    resident_notifications: {
      repair_started: d.repair_started,
      maintenance_started: d.maintenance_started,
      back_in_service: d.back_in_service,
    },
    staff_reminders: {
      maintenance: parseIntList(d.maintenance),
      certification: parseIntList(d.certification),
      contract: parseIntList(d.contract),
      overdue_weekly: d.overdue_weekly,
    },
  }
}

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

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-3">
      <h2 className="text-[13px] font-semibold text-text-primary">{title}</h2>
      {children}
    </div>
  )
}

export default function ElevatorsConfigPage() {
  const { t } = useTranslation()
  usePageTitle(t('elevators.config.title'))
  const config = useElevatorsConfig()
  const save = useSaveElevatorsConfig()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [seededFrom, setSeededFrom] = useState<ElevatorsConfigOut | null>(null)
  if (config.data && config.data !== seededFrom) {
    setSeededFrom(config.data)
    if (draft === null) setDraft(draftFrom(config.data))
  }

  if (config.isLoading || (!draft && !config.isError)) return <LoadingSpinner />
  if (config.isError || !draft || !config.data) {
    return <div className="p-6"><p className="text-[13px] text-red">{t('common.error')}</p></div>
  }

  const patch = (p: Partial<Draft>) => setDraft((prev) => (prev ? { ...prev, ...p } : prev))

  const submit = () => {
    const listsOk = [draft.maintenance, draft.certification, draft.contract].every((s) => INT_LIST_RE.test(s))
    if (!listsOk) {
      setError(t('elevators.config.invalidStages'))
      return
    }
    setError(null)
    save.mutate(toPayload(draft))
  }

  const numberField = (id: keyof Pick<Draft, 'not_working' | 'under_repair'>, labelKey: string) => (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={`cfg-${id}`}>{t(labelKey)}</Label>
      <Input
        id={`cfg-${id}`} type="number" min="1" value={draft[id]}
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

      <Card title={t('elevators.config.thresholds')}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {numberField('not_working', 'elevators.config.notWorkingDays')}
          {numberField('under_repair', 'elevators.config.underRepairDays')}
        </div>
      </Card>

      <Card title={t('elevators.config.residentNotifications')}>
        <Toggle id="cfg-repair_started" label={t('elevators.config.repairStarted')} checked={draft.repair_started} onChange={(v) => patch({ repair_started: v })} />
        <Toggle id="cfg-maintenance_started" label={t('elevators.config.maintenanceStarted')} checked={draft.maintenance_started} onChange={(v) => patch({ maintenance_started: v })} />
        <Toggle id="cfg-back_in_service" label={t('elevators.config.backInService')} checked={draft.back_in_service} onChange={(v) => patch({ back_in_service: v })} />
      </Card>

      <Card title={t('elevators.config.staffReminders')}>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {listField('maintenance', 'elevators.config.maintenance')}
          {listField('certification', 'elevators.config.certification')}
          {listField('contract', 'elevators.config.contract')}
        </div>
        <Toggle id="cfg-overdue_weekly" label={t('elevators.config.overdueWeekly')} checked={draft.overdue_weekly} onChange={(v) => patch({ overdue_weekly: v })} />
      </Card>

      <Card title={t('elevators.config.modulePublic')}>
        <Toggle
          id="cfg-module_public" label={t('elevators.config.modulePublic')} checked={config.data.module_public}
          onChange={() => undefined} disabled hint={t('elevators.config.modulePublicHint')}
        />
      </Card>

      {error && <p role="alert" className="text-[13px] text-red">{error}</p>}

      <div>
        <Button onClick={submit} disabled={save.isPending}>
          {save.isPending ? t('common.saving') : t('common.save')}
        </Button>
      </div>
    </div>
  )
}
