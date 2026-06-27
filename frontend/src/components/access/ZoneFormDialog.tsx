import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
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
import { Select } from '@/components/ui/select'
import type { CreateZonePayload, OfflineMode, ZoneRow } from '../../types/access'

/**
 * Диалог создания/редактирования зоны. Помимо полей зоны (code/name/description/
 * offline_mode/лимит постоянных) в режиме редактирования управляет привязкой фаз
 * (yards): текущий список с кнопкой удаления + ввод yard_id для добавления.
 *
 * Привязка фаз идёт отдельным запросом (POST /admin/zones/{id}/yards) — вызывается
 * сразу через onAddYard/onRemoveYard, а не копится в форме (у создаваемой зоны
 * ещё нет id). Поля зоны сохраняются по кнопке submit (POST/PATCH).
 */
const OFFLINE_MODES: OfflineMode[] = ['fail_closed', 'cached_permanent_only']

interface Props {
  open: boolean
  /** Редактируемая зона (null → создание новой). */
  zone?: ZoneRow | null
  /** Актуальный список фаз зоны (из query, обновляется после мутаций). */
  yardIds?: number[]
  loading?: boolean
  yardsLoading?: boolean
  onClose: () => void
  onSubmit: (payload: CreateZonePayload) => void
  onAddYard?: (yardId: number) => void
  onRemoveYard?: (yardId: number) => void
}

interface FormState {
  code: string
  name: string
  description: string
  offlineMode: OfflineMode
  maxPermanent: string
  isActive: boolean
}

function initialState(zone?: ZoneRow | null): FormState {
  return {
    code: zone?.code ?? '',
    name: zone?.name ?? '',
    description: zone?.description ?? '',
    offlineMode: zone?.offline_mode ?? 'fail_closed',
    maxPermanent: zone?.max_permanent_per_apartment != null ? String(zone.max_permanent_per_apartment) : '',
    isActive: zone?.is_active ?? true,
  }
}

export default function ZoneFormDialog({
  open,
  zone,
  yardIds = [],
  loading,
  yardsLoading,
  onClose,
  onSubmit,
  onAddYard,
  onRemoveYard,
}: Props) {
  const { t } = useTranslation()
  const isEdit = Boolean(zone)
  const [form, setForm] = useState<FormState>(() => initialState(zone))
  const [yardInput, setYardInput] = useState('')

  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setForm(initialState(zone))
      setYardInput('')
    }
  }

  const set = (patch: Partial<FormState>) => setForm((p) => ({ ...p, ...patch }))
  const canSubmit = form.code.trim().length > 0 && form.name.trim().length > 0 && !loading

  function handleSubmit() {
    if (!canSubmit) return
    const maxN = Number(form.maxPermanent)
    const payload: CreateZonePayload = {
      code: form.code.trim(),
      name: form.name.trim(),
      offline_mode: form.offlineMode,
      description: form.description.trim() || undefined,
      max_permanent_per_apartment:
        form.maxPermanent.trim() && Number.isFinite(maxN) ? maxN : undefined,
      ...(isEdit ? { is_active: form.isActive } : {}),
    }
    onSubmit(payload)
  }

  function addYard() {
    const n = Number(yardInput.trim())
    if (yardInput.trim() && Number.isFinite(n) && !yardIds.includes(n)) {
      onAddYard?.(n)
      setYardInput('')
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit
              ? t('accessControl.equipment.zoneForm.editTitle')
              : t('accessControl.equipment.zoneForm.createTitle')}
          </DialogTitle>
          <DialogDescription>{t('accessControl.equipment.zoneForm.desc')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="zf-code">{t('accessControl.equipment.fields.code')}</Label>
              <Input
                id="zf-code"
                value={form.code}
                onChange={(e) => set({ code: e.target.value })}
                className="font-mono"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="zf-name">{t('accessControl.equipment.fields.name')}</Label>
              <Input id="zf-name" value={form.name} onChange={(e) => set({ name: e.target.value })} />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="zf-desc">{t('accessControl.equipment.fields.description')}</Label>
            <Input
              id="zf-desc"
              value={form.description}
              onChange={(e) => set({ description: e.target.value })}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="zf-offline">{t('accessControl.equipment.fields.offlineMode')}</Label>
              <Select
                id="zf-offline"
                value={form.offlineMode}
                onChange={(e) => set({ offlineMode: e.target.value as OfflineMode })}
              >
                {OFFLINE_MODES.map((m) => (
                  <option key={m} value={m}>
                    {t(`accessControl.equipment.offlineMode.${m}`)}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="zf-max">{t('accessControl.equipment.fields.maxPermanent')}</Label>
              <Input
                id="zf-max"
                type="number"
                value={form.maxPermanent}
                onChange={(e) => set({ maxPermanent: e.target.value })}
              />
            </div>
          </div>

          {isEdit && (
            <label className="flex items-center gap-2 text-[13px] text-text-primary">
              <input
                type="checkbox"
                checked={form.isActive}
                onChange={(e) => set({ isActive: e.target.checked })}
                className="h-4 w-4 accent-[var(--accent)]"
              />
              {t('accessControl.equipment.fields.isActive')}
            </label>
          )}

          {/* Привязка фаз — только в режиме редактирования (нужен id зоны). */}
          {isEdit && (
            <div className="flex flex-col gap-2 rounded-default border border-border-default p-3">
              <div className="text-[12px] font-semibold text-text-secondary">
                {t('accessControl.equipment.zoneForm.yardsLabel')}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {yardIds.length === 0 ? (
                  <span className="text-[12px] text-text-muted">
                    {t('accessControl.equipment.zoneForm.noYards')}
                  </span>
                ) : (
                  yardIds.map((yid) => (
                    <span
                      key={yid}
                      className="inline-flex items-center gap-1 rounded-full bg-bg-surface px-2.5 py-0.5 text-[12px] text-text-primary"
                    >
                      #{yid}
                      <button
                        type="button"
                        onClick={() => onRemoveYard?.(yid)}
                        disabled={yardsLoading}
                        aria-label={t('accessControl.equipment.zoneForm.removeYard', { id: yid })}
                        className="text-text-muted hover:text-red"
                      >
                        <X size={12} />
                      </button>
                    </span>
                  ))
                )}
              </div>
              <div className="flex items-end gap-2">
                <Input
                  type="number"
                  value={yardInput}
                  onChange={(e) => setYardInput(e.target.value)}
                  placeholder={t('accessControl.equipment.zoneForm.yardPlaceholder')}
                  className="w-[140px]"
                />
                <Button variant="outline" size="sm" disabled={yardsLoading} onClick={addYard}>
                  {t('accessControl.equipment.zoneForm.addYard')}
                </Button>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!canSubmit} onClick={handleSubmit}>
            {loading
              ? isEdit
                ? t('common.saving')
                : t('common.creating')
              : isEdit
                ? t('common.save')
                : t('accessControl.equipment.add')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
