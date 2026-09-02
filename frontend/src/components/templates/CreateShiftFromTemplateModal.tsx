import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usePersonName, type PersonNameFormatter } from '../../hooks/usePersonName'
import { useCreateShiftFromTemplate } from '../../hooks/useTemplates'
import { useEmployees } from '../../hooks/useEmployees'
import { tSpecialization } from '../../i18n/apiMaps'
import type { EmployeeBrief } from '../../types/api'
import { todayInDisplayTz } from '../../utils/timezone'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface Props {
  isOpen: boolean
  onClose: () => void
  templateId: number | null
  templateName?: string
  /** Требуемые специализации шаблона: сервер вернёт только подходящих
   *  исполнителей (семантика guard'а шаблонов, джокер `universal`). Пустой
   *  список = шаблон без ограничений — показываются все. */
  requiredSpecializations?: string[]
}

function employeeName(e: EmployeeBrief, fullName: PersonNameFormatter['full']): string {
  return fullName(e) || e.phone || `#${e.id}`
}

// ARCH-137 B7: дефолт даты — день объекта (display-зона), а не UTC-день
// (`toISOString` вечером по Ташкенту давал вчерашнюю дату).
function today(): string {
  return todayInDisplayTz()
}

export default function CreateShiftFromTemplateModal({
  isOpen,
  onClose,
  templateId,
  templateName,
  requiredSpecializations = [],
}: Props) {
  const { t } = useTranslation()
  const { full: fullName } = usePersonName()
  const createFromTemplate = useCreateShiftFromTemplate()
  const { data: employees = [], isLoading } = useEmployees({
    ...(requiredSpecializations.length > 0
      ? { for_specializations: requiredSpecializations.join(',') }
      : {}),
  })

  const [date, setDate] = useState(today)
  const [selected, setSelected] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)

  // Reset to defaults each time the modal is (re)opened so a previous row's
  // selection never leaks into the next create.
  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- намеренный сброс полей к дефолтам при открытии модалки
      setDate(today())
      setSelected([])
      setError(null)
    }
  }, [isOpen])

  const toggle = (id: number) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const handleSubmit = () => {
    setError(null)
    if (!date) {
      setError(t('errors.shiftDateRequired'))
      return
    }
    if (selected.length === 0) {
      setError(t('errors.executorsRequired'))
      return
    }
    if (templateId == null) return
    createFromTemplate.mutate(
      { template_id: templateId, date, user_ids: selected },
      { onSuccess: () => onClose() },
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('templates.createShiftTitle')}
            {templateName ? ` — ${templateName}` : ''}
          </DialogTitle>
        </DialogHeader>

        {/* min-w-0 обязателен: DialogContent — grid, и intrinsic-ширина
            nowrap-бейджей специализаций иначе распирает auto-колонку шире
            панели (grid blowout) — min-w-0 на вложенных span'ах сжимает их
            при layout, но НЕ уменьшает min-content-вклад грид-итема. */}
        <div className="space-y-4 min-w-0">
          <div className="space-y-1.5">
            <Label>{t('templates.shiftDate')}</Label>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between">
              <Label>{t('templates.selectExecutors')}</Label>
              {selected.length > 0 && (
                <span className="text-xs text-text-muted">
                  {t('templates.selectedCount', { count: selected.length })}
                </span>
              )}
            </div>
            {requiredSpecializations.length > 0 && (
              <p className="text-xs text-text-muted m-0">
                {t('templates.executorsFilteredBySpecs', {
                  specs: requiredSpecializations
                    .map((s) => tSpecialization(s, t))
                    .join(', '),
                })}
              </p>
            )}
            {isLoading ? (
              <p className="text-[13px] text-muted-foreground">{t('common.loading')}</p>
            ) : employees.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">{t('templates.noExecutors')}</p>
            ) : (
              <div className="max-h-64 overflow-y-auto border border-border-default rounded-sm divide-y divide-border-default">
                {employees.map((e) => (
                  <label
                    key={e.id}
                    className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-bg-surface transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(e.id)}
                      onChange={() => toggle(e.id)}
                    />
                    <span className="flex-1 min-w-0 text-[13px] text-text-primary">
                      {employeeName(e, fullName)}
                      {e.active_shift_id !== null && (
                        <span className="ml-2 text-xs text-emerald whitespace-nowrap">
                          ● {t('kanban.onShift')}
                        </span>
                      )}
                    </span>
                    {e.specialization.length > 0 && (
                      // min-w-0 обязателен: с nowrap-эллипсисом без него
                      // min-content строки = полная ширина списка специализаций,
                      // и auto-колонка грида DialogContent распирается шире
                      // панели (вёрстка «уезжала» на длинных наборах).
                      <span className="text-[11px] text-text-muted text-right min-w-0 max-w-[45%] truncate">
                        {e.specialization.map((s) => tSpecialization(s, t)).join(', ')}
                      </span>
                    )}
                  </label>
                ))}
              </div>
            )}
          </div>

          {error && (
            <div className="text-[13px] text-red bg-red/10 border border-red/30 rounded-sm px-3 py-2.5">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={createFromTemplate.isPending}>
            {createFromTemplate.isPending ? t('common.creating') : t('templates.createShift')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
