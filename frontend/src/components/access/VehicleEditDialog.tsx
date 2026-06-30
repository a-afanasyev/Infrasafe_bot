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
import { useAccessVehicleDetail } from '../../hooks/useAccessRegistry'
import LoadingSpinner from '../shared/LoadingSpinner'
import ZoneCheckboxes from './ZoneCheckboxes'
import type {
  UpdateVehiclePayload,
  VehicleDetail,
  VehicleRelationType,
  ZoneRef,
} from '../../types/access'

/**
 * Диалог правки карточки авто (PATCH /vehicles/{id}): атрибуты + гос. номер +
 * привязка владельца (квартира + отношение). Деталь грузится по id; отправляются
 * все редактируемые поля (PATCH применит, дубль номера → 409 наверх).
 */
interface Props {
  vehicleId: number | null
  loading?: boolean
  onClose: () => void
  onSubmit: (payload: UpdateVehiclePayload) => void
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
  zoneIds: number[]
}

/** Кандидаты-зоны: обслуживающие зоны квартир авто + уже выданные явные (rule_zones). */
function candidateZones(detail: VehicleDetail): ZoneRef[] {
  const map = new Map<number, ZoneRef>()
  for (const ap of detail.apartment_details) for (const z of ap.zones) map.set(z.id, z)
  for (const z of detail.rule_zones) if (!map.has(z.id)) map.set(z.id, z)
  return [...map.values()].sort((a, b) => a.id - b.id)
}

function initial(detail: VehicleDetail): FormState {
  const v = detail.vehicle
  const owner = detail.apartment_details.find((a) => a.status === 'active')
  return {
    plate: v.plate_number_original || v.plate_number_normalized || '',
    country: v.plate_country ?? '',
    plateType: v.plate_type ?? '',
    brand: v.brand ?? '',
    model: v.model ?? '',
    color: v.color ?? '',
    vehicleClass: v.vehicle_class ?? '',
    apartmentId: owner ? String(owner.apartment_id) : '',
    relationType: owner?.relation_type ?? '',
    zoneIds: detail.rule_zones.map((z) => z.id),
  }
}

const BLANK: FormState = {
  plate: '', country: '', plateType: '', brand: '', model: '', color: '',
  vehicleClass: '', apartmentId: '', relationType: '', zoneIds: [],
}

export default function VehicleEditDialog({ vehicleId, loading, onClose, onSubmit }: Props) {
  const { t } = useTranslation()
  const open = vehicleId !== null
  const { data: detail, isLoading } = useAccessVehicleDetail(vehicleId)
  const [form, setForm] = useState<FormState>(BLANK)

  // Префилл при загрузке карточки (render-time sync по vehicle.id).
  const [syncId, setSyncId] = useState<number | null>(null)
  if (detail && detail.vehicle.id !== syncId) {
    setSyncId(detail.vehicle.id)
    setForm(initial(detail))
  }

  const set = (patch: Partial<FormState>) => setForm((p) => ({ ...p, ...patch }))
  const trimmedOrNull = (s: string) => (s.trim() ? s.trim() : null)
  const canSubmit = form.plate.trim().length > 0 && !loading

  function handleSubmit() {
    if (!canSubmit) return
    const payload: UpdateVehiclePayload = {
      plate_number_original: form.plate.trim(),
      plate_country: trimmedOrNull(form.country),
      plate_type: trimmedOrNull(form.plateType),
      brand: trimmedOrNull(form.brand),
      model: trimmedOrNull(form.model),
      color: trimmedOrNull(form.color),
      vehicle_class: trimmedOrNull(form.vehicleClass),
      zone_ids: form.zoneIds,
    }
    const apt = Number(form.apartmentId)
    if (form.apartmentId.trim() && Number.isFinite(apt)) {
      payload.apartment_id = apt
      if (form.relationType.trim()) {
        payload.relation_type = form.relationType.trim() as VehicleRelationType
      }
    }
    onSubmit(payload)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('accessControl.vehicleEdit.title')}</DialogTitle>
          <DialogDescription>{t('accessControl.vehicleEdit.desc')}</DialogDescription>
        </DialogHeader>

        {isLoading && !detail && <LoadingSpinner />}

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ve-plate">{t('accessControl.vehicleForm.plate')}</Label>
            <Input
              id="ve-plate"
              value={form.plate}
              onChange={(e) => set({ plate: e.target.value })}
              className="font-mono"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ve-brand">{t('accessControl.vehicleForm.brand')}</Label>
              <Input id="ve-brand" value={form.brand} onChange={(e) => set({ brand: e.target.value })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ve-model">{t('accessControl.vehicleForm.model')}</Label>
              <Input id="ve-model" value={form.model} onChange={(e) => set({ model: e.target.value })} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ve-color">{t('accessControl.vehicleForm.color')}</Label>
              <Input id="ve-color" value={form.color} onChange={(e) => set({ color: e.target.value })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ve-class">{t('accessControl.vehicleForm.class')}</Label>
              <Input
                id="ve-class"
                value={form.vehicleClass}
                onChange={(e) => set({ vehicleClass: e.target.value })}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ve-country">{t('accessControl.vehicleForm.country')}</Label>
              <Input
                id="ve-country"
                value={form.country}
                onChange={(e) => set({ country: e.target.value })}
                placeholder="UZ"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ve-plateType">{t('accessControl.vehicleForm.plateType')}</Label>
              <Input
                id="ve-plateType"
                value={form.plateType}
                onChange={(e) => set({ plateType: e.target.value })}
              />
            </div>
          </div>

          <div className="border-t border-border-default pt-3 flex flex-col gap-3">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-text-secondary">
              {t('accessControl.vehicleEdit.owner')}
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ve-apartment">{t('accessControl.vehicleForm.apartmentId')}</Label>
                <Input
                  id="ve-apartment"
                  type="number"
                  value={form.apartmentId}
                  onChange={(e) => set({ apartmentId: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ve-relation">{t('accessControl.vehicleForm.relationType')}</Label>
                <Select
                  id="ve-relation"
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
          </div>

          <div className="border-t border-border-default pt-3 flex flex-col gap-2">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-text-secondary">
              {t('accessControl.vehicleEdit.zones')}
            </h3>
            <p className="text-[12px] text-text-muted">
              {t('accessControl.vehicleEdit.zonesHint')}
            </p>
            {detail && (
              <ZoneCheckboxes
                zones={candidateZones(detail)}
                selected={form.zoneIds}
                onChange={(ids) => set({ zoneIds: ids })}
                emptyText={t('accessControl.vehicleEdit.noZones')}
              />
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!canSubmit} onClick={handleSubmit}>
            {loading ? t('common.saving') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
