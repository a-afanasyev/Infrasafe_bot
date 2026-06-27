import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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

/**
 * Декларативная диалог-форма раздела «Оборудование» (въезды/камеры/шлагбаумы/
 * контроллеры). Поля задаются схемой `fields`; форма сама собирает payload:
 * пустые text/number/csv → не отправляются (бэкенд принимает их опционально).
 *
 * Зоны используют отдельный ZoneFormDialog (привязка фаз). JSON-поля
 * (attributes/config) в пилоте не редактируются — вне scope формы.
 */
// 'numberSelect' — выпадающий список, значение которого отправляется числом
// (напр. zone_id/gate_id: опции строковые, payload — number).
export type FieldType = 'text' | 'number' | 'select' | 'numberSelect' | 'checkbox' | 'csv'

export interface FormField {
  name: string
  type: FieldType
  label: string
  placeholder?: string
  required?: boolean
  /** Для type='select'. */
  options?: { value: string; label: string }[]
  /** Поле показывается только в режиме редактирования (напр. is_active). */
  editOnly?: boolean
}

type FieldValue = string | boolean
type FormState = Record<string, FieldValue>

interface Props {
  open: boolean
  title: string
  description?: string
  fields: FormField[]
  /** Значения для режима редактирования (id присутствует → edit). */
  initial?: Record<string, unknown> | null
  loading?: boolean
  onClose: () => void
  onSubmit: (payload: Record<string, unknown>) => void
}

function toFieldValue(type: FieldType, raw: unknown): FieldValue {
  if (type === 'checkbox') return raw === undefined ? true : Boolean(raw)
  if (type === 'csv') return Array.isArray(raw) ? raw.join(', ') : raw == null ? '' : String(raw)
  return raw == null ? '' : String(raw)
}

function buildInitialState(fields: FormField[], initial?: Record<string, unknown> | null): FormState {
  const state: FormState = {}
  for (const f of fields) {
    state[f.name] = toFieldValue(f.type, initial?.[f.name])
  }
  return state
}

export default function EquipmentFormDialog({
  open,
  title,
  description,
  fields,
  initial,
  loading,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const isEdit = Boolean(initial)
  const visibleFields = fields.filter((f) => !f.editOnly || isEdit)

  const [form, setForm] = useState<FormState>(() => buildInitialState(fields, initial))

  // Сброс формы при открытии (render-time, как в VehicleFormDialog).
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) setForm(buildInitialState(fields, initial))
  }

  const set = (name: string, value: FieldValue) => setForm((p) => ({ ...p, [name]: value }))

  const requiredOk = visibleFields.every((f) => {
    if (!f.required) return true
    const v = form[f.name]
    return typeof v === 'string' ? v.trim().length > 0 : true
  })
  const canSubmit = requiredOk && !loading

  function handleSubmit() {
    if (!canSubmit) return
    const payload: Record<string, unknown> = {}
    for (const f of visibleFields) {
      const v = form[f.name]
      if (f.type === 'checkbox') {
        payload[f.name] = Boolean(v)
      } else if (f.type === 'number' || f.type === 'numberSelect') {
        const s = String(v).trim()
        const n = Number(s)
        if (s && Number.isFinite(n)) payload[f.name] = n
      } else if (f.type === 'csv') {
        const parts = String(v)
          .split(',')
          .map((p) => p.trim())
          .filter(Boolean)
        if (parts.length > 0) payload[f.name] = parts
      } else {
        const s = String(v).trim()
        if (s) payload[f.name] = s
      }
    }
    onSubmit(payload)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        <div className="flex flex-col gap-3">
          {visibleFields.map((f) => {
            const id = `eq-${f.name}`
            if (f.type === 'checkbox') {
              return (
                <label key={f.name} className="flex items-center gap-2 text-[13px] text-text-primary">
                  <input
                    id={id}
                    type="checkbox"
                    checked={Boolean(form[f.name])}
                    onChange={(e) => set(f.name, e.target.checked)}
                    className="h-4 w-4 accent-[var(--accent)]"
                  />
                  {f.label}
                </label>
              )
            }
            if (f.type === 'select' || f.type === 'numberSelect') {
              return (
                <div key={f.name} className="flex flex-col gap-1.5">
                  <Label htmlFor={id}>{f.label}</Label>
                  <Select
                    id={id}
                    value={String(form[f.name] ?? '')}
                    onChange={(e) => set(f.name, e.target.value)}
                  >
                    {!f.required && <option value="">—</option>}
                    {f.options?.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </Select>
                </div>
              )
            }
            return (
              <div key={f.name} className="flex flex-col gap-1.5">
                <Label htmlFor={id}>{f.label}</Label>
                <Input
                  id={id}
                  type={f.type === 'number' ? 'number' : 'text'}
                  value={String(form[f.name] ?? '')}
                  onChange={(e) => set(f.name, e.target.value)}
                  placeholder={f.placeholder}
                  className={f.name === 'code' || f.name === 'controller_uid' ? 'font-mono' : undefined}
                />
              </div>
            )
          })}
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
