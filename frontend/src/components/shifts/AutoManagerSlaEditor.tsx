import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import type { AutoManagerSlaConfig } from '../../types/autoManagerConfig'

// Редактор SLA-лестницы ИИ-менеджера: целые ≥ 0 (0 = выключено), диапазоны
// проверяет бэкенд (`validate_config`). Черновик — отдельно от конфига, как
// окно работы в AutoManagerCard: ресид только пока пользователь не правил.
interface SlaEditorProps {
  value: AutoManagerSlaConfig
  pending: boolean
  onSave: (sla: AutoManagerSlaConfig) => void
}

const URGENCIES = ['critical', 'high', 'medium', 'low'] as const
const LADDER = ['remind_executor', 'staff_group', 'manager', 'reassign'] as const
const SINGLES = [
  'clarification_max',
  'executed_unconfirmed_max',
  'completed_unaccepted_days',
  'critical_unassigned_minutes',
] as const

function toInt(raw: string): number {
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) && n >= 0 ? n : 0
}

export default function SlaEditor({ value, pending, onSave }: SlaEditorProps) {
  const { t } = useTranslation()
  const [seededFrom, setSeededFrom] = useState<AutoManagerSlaConfig | null>(null)
  const [draft, setDraft] = useState<AutoManagerSlaConfig>(value)

  if (value !== seededFrom) {
    const untouched = seededFrom === null || JSON.stringify(draft) === JSON.stringify(seededFrom)
    setSeededFrom(value)
    if (untouched) setDraft(value)
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(value)

  const field = (label: string, current: number, onChange: (n: number) => void, suffix: string) => (
    <label className="flex items-center justify-between gap-2 text-[11px] text-text-muted">
      <span className="truncate">{label}</span>
      <span className="flex items-center gap-1">
        <Input
          type="number"
          min={0}
          className="w-16 h-7 text-xs"
          value={current}
          aria-label={label}
          onChange={(e) => onChange(toInt(e.target.value))}
        />
        <span className="w-6">{suffix}</span>
      </span>
    </label>
  )

  return (
    <div className="flex flex-col gap-2 border-t border-border-default pt-3">
      <span className="text-[11px] text-text-muted">{t('autoManager.sla.title')}</span>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold text-text-primary">{t('autoManager.sla.inProgress')}</span>
          {URGENCIES.map((u) =>
            field(
              t(`autoManager.sla.urgency.${u}`),
              draft.in_progress_max[u],
              (n) => setDraft({ ...draft, in_progress_max: { ...draft.in_progress_max, [u]: n } }),
              t('autoManager.sla.h'),
            ),
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold text-text-primary">{t('autoManager.sla.ladder')}</span>
          {LADDER.map((step) =>
            field(
              t(`autoManager.sla.step.${step}`),
              draft.ladder[step],
              (n) => setDraft({ ...draft, ladder: { ...draft.ladder, [step]: n } }),
              t('autoManager.sla.h'),
            ),
          )}
        </div>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          {SINGLES.map((key) =>
            field(
              t(`autoManager.sla.${key}`),
              draft[key],
              (n) => setDraft({ ...draft, [key]: n }),
              t(key === 'completed_unaccepted_days' ? 'autoManager.sla.d'
                : key === 'critical_unassigned_minutes' ? 'autoManager.sla.min' : 'autoManager.sla.h'),
            ),
          )}
        </div>
      </div>
      <div>
        <Button variant="outline" size="sm" disabled={!dirty || pending} onClick={() => onSave(draft)}>
          {t('autoManager.sla.save')}
        </Button>
      </div>
    </div>
  )
}
