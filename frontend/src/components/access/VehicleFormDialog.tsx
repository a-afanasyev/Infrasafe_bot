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
import type { CreateVehiclePayload, VehicleRelationType } from '../../types/access'

/**
 * Диалог-форма создания авто менеджером (POST /vehicles). Обязателен только
 * гос. номер; квартира/зона — числовой ввод, отношение — select. Пустые поля не
 * отправляются (бэкенд принимает их опционально).
 */
interface Props {
  open: boolean
  loading?: boolean
  onClose: () => void
  onSubmit: (payload: CreateVehiclePayload) => void
}

const RELATION_TYPES: VehicleRelationType[] = ['owner', 'tenant', 'family', 'service']

interface FormState {
  plate: string
  country: string
  plateType: string
  brand: string
  model: string
  color: string
  vehicleClass: string
  apartmentId: string
  relationType: string
  zoneId: string
}

const EMPTY: FormState = {
  plate: '',
  country: '',
  plateType: '',
  brand: '',
  model: '',
  color: '',
  vehicleClass: '',
  apartmentId: '',
  relationType: '',
  zoneId: '',
}

export default function VehicleFormDialog({ open, loading, onClose, onSubmit }: Props) {
  const { t } = useTranslation()
  const [form, setForm] = useState<FormState>(EMPTY)

  // Сброс формы при открытии (render-time, как в ResolveDialog).
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) setForm(EMPTY)
  }

  const set = (patch: Partial<FormState>) => setForm((p) => ({ ...p, ...patch }))
  const trimmed = (s: string) => (s.trim() ? s.trim() : undefined)
  const numeric = (s: string) => {
    const n = Number(s)
    return s.trim() && Number.isFinite(n) ? n : undefined
  }

  const canSubmit = form.plate.trim().length > 0 && !loading

  function handleSubmit() {
    if (!canSubmit) return
    const payload: CreateVehiclePayload = {
      plate_number_original: form.plate.trim(),
      plate_country: trimmed(form.country),
      plate_type: trimmed(form.plateType),
      brand: trimmed(form.brand),
      model: trimmed(form.model),
      color: trimmed(form.color),
      vehicle_class: trimmed(form.vehicleClass),
      apartment_id: numeric(form.apartmentId),
      relation_type: (trimmed(form.relationType) as VehicleRelationType) ?? undefined,
      zone_id: numeric(form.zoneId),
    }
    onSubmit(payload)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('accessControl.vehicleForm.title')}</DialogTitle>
          <DialogDescription>{t('accessControl.vehicleForm.desc')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="vf-plate">{t('accessControl.vehicleForm.plate')}</Label>
            <Input
              id="vf-plate"
              value={form.plate}
              onChange={(e) => set({ plate: e.target.value })}
              placeholder={t('accessControl.vehicleForm.platePlaceholder')}
              className="font-mono"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="vf-brand">{t('accessControl.vehicleForm.brand')}</Label>
              <Input id="vf-brand" value={form.brand} onChange={(e) => set({ brand: e.target.value })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="vf-model">{t('accessControl.vehicleForm.model')}</Label>
              <Input id="vf-model" value={form.model} onChange={(e) => set({ model: e.target.value })} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="vf-color">{t('accessControl.vehicleForm.color')}</Label>
              <Input id="vf-color" value={form.color} onChange={(e) => set({ color: e.target.value })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="vf-class">{t('accessControl.vehicleForm.class')}</Label>
              <Input
                id="vf-class"
                value={form.vehicleClass}
                onChange={(e) => set({ vehicleClass: e.target.value })}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="vf-country">{t('accessControl.vehicleForm.country')}</Label>
              <Input
                id="vf-country"
                value={form.country}
                onChange={(e) => set({ country: e.target.value })}
                placeholder="UZ"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="vf-plateType">{t('accessControl.vehicleForm.plateType')}</Label>
              <Input
                id="vf-plateType"
                value={form.plateType}
                onChange={(e) => set({ plateType: e.target.value })}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="vf-apartment">{t('accessControl.vehicleForm.apartmentId')}</Label>
              <Input
                id="vf-apartment"
                type="number"
                value={form.apartmentId}
                onChange={(e) => set({ apartmentId: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="vf-zone">{t('accessControl.vehicleForm.zoneId')}</Label>
              <Input
                id="vf-zone"
                type="number"
                value={form.zoneId}
                onChange={(e) => set({ zoneId: e.target.value })}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="vf-relation">{t('accessControl.vehicleForm.relationType')}</Label>
            <Select
              id="vf-relation"
              value={form.relationType}
              onChange={(e) => set({ relationType: e.target.value })}
            >
              <option value="">{t('accessControl.vehicleForm.relationNone')}</option>
              {RELATION_TYPES.map((rt) => (
                <option key={rt} value={rt}>
                  {t(`accessControl.relationType.${rt}`, { defaultValue: rt })}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!canSubmit} onClick={handleSubmit}>
            {loading ? t('common.creating') : t('accessControl.vehicleForm.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
