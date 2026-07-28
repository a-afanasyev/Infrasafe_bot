import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAttachApartment } from '../../hooks/useResidents'
import { useYards, useAllBuildings, useAllApartments } from '../../hooks/useAddresses'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'

interface Props {
  residentId: number
  onClose: () => void
}

// Родитель монтирует модалку только когда она открыта, поэтому состояние
// выбора сбрасывается размонтированием. Держать `open` пропом и чистить поля
// эффектом значило бы setState внутри эффекта — каскадный ререндер, который
// линтер запрещает, и лишний источник рассинхрона.

export default function AttachApartmentModal({ residentId, onClose }: Props) {
  const { t } = useTranslation()
  const [yardId, setYardId] = useState<number | null>(null)
  const [buildingId, setBuildingId] = useState<number | null>(null)
  const [apartmentId, setApartmentId] = useState<number | null>(null)
  const [isOwner, setIsOwner] = useState(false)
  const [isPrimary, setIsPrimary] = useState(false)

  const attach = useAttachApartment(residentId)

  const { data: yards = [] } = useYards()
  const { data: buildings = [] } = useAllBuildings(yardId)
  const { data: apartments = [] } = useAllApartments(yardId, buildingId)

  const submit = () => {
    if (apartmentId === null) return
    attach.mutate(
      { apartment_id: apartmentId, is_owner: isOwner, is_primary: isPrimary },
      { onSuccess: onClose },
    )
  }

  return (
    <Dialog open onOpenChange={o => { if (!o) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('residents.attachTitle')}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>{t('residents.yard')}</Label>
            <Select
              value={yardId ?? ''}
              onChange={e => {
                setYardId(e.target.value ? Number(e.target.value) : null)
                setBuildingId(null)
                setApartmentId(null)
              }}
            >
              <option value="">{t('residents.selectYard')}</option>
              {yards.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>{t('residents.building')}</Label>
            <Select
              value={buildingId ?? ''}
              disabled={yardId === null}
              onChange={e => {
                setBuildingId(e.target.value ? Number(e.target.value) : null)
                setApartmentId(null)
              }}
            >
              <option value="">{t('residents.selectBuilding')}</option>
              {buildings.map(b => <option key={b.id} value={b.id}>{b.address}</option>)}
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>{t('residents.apartment')}</Label>
            <Select
              value={apartmentId ?? ''}
              disabled={buildingId === null}
              onChange={e => setApartmentId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">{t('residents.selectApartment')}</option>
              {apartments.map(a => (
                <option key={a.id} value={a.id}>{a.apartment_number}</option>
              ))}
            </Select>
          </div>

          <label className="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer">
            <input type="checkbox" checked={isOwner} onChange={e => setIsOwner(e.target.checked)} />
            {t('residents.isOwner')}
          </label>
          <label className="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer">
            <input type="checkbox" checked={isPrimary} onChange={e => setIsPrimary(e.target.checked)} />
            {t('residents.makePrimary')}
          </label>
          <p className="text-[11px] text-text-muted m-0">
            {t('residents.attachHint')}
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={apartmentId === null || attach.isPending}>
            {t('residents.attachSubmit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
