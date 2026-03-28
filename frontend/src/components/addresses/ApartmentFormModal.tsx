import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useCreateApartment, useUpdateApartment } from '../../hooks/useAddresses'
import type { ApartmentBrief } from '../../types/api'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'

interface Props {
  apartment?: ApartmentBrief
  buildingId: number
  onClose: () => void
}

export default function ApartmentFormModal({ apartment, buildingId, onClose }: Props) {
  const { t } = useTranslation()
  const [apartmentNumber, setApartmentNumber] = useState(apartment?.apartment_number ?? '')
  const [entrance, setEntrance] = useState<string>(apartment?.entrance != null ? String(apartment.entrance) : '')
  const [floor, setFloor] = useState<string>(apartment?.floor != null ? String(apartment.floor) : '')
  const [roomsCount, setRoomsCount] = useState<string>(apartment?.rooms_count != null ? String(apartment.rooms_count) : '')
  const [area, setArea] = useState<string>(apartment?.area != null ? String(apartment.area) : '')
  const [description, setDescription] = useState(apartment?.description ?? '')

  const createApartment = useCreateApartment()
  const updateApartment = useUpdateApartment()
  const mutation = apartment ? updateApartment : createApartment

  const handleSubmit = () => {
    if (!apartmentNumber.trim()) return

    const payload = {
      building_id: buildingId,
      apartment_number: apartmentNumber.trim(),
      entrance: entrance ? parseInt(entrance) || null : null,
      floor: floor ? parseInt(floor) || null : null,
      rooms_count: roomsCount ? parseInt(roomsCount) || null : null,
      area: area ? parseFloat(area) || null : null,
      description: description.trim() || null,
    }

    if (apartment) {
      updateApartment.mutate(
        { id: apartment.id, ...payload },
        { onSuccess: onClose },
      )
    } else {
      createApartment.mutate(
        { ...payload, is_active: true },
        { onSuccess: onClose },
      )
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{apartment ? t('addressForms.editApartment') : t('addressForms.newApartment')}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div>
            <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.aptNumberLabel')}</Label>
            <Input
              value={apartmentNumber}
              onChange={e => setApartmentNumber(e.target.value)}
              autoFocus
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.entranceLabel')}</Label>
              <Input
                type="number"
                value={entrance}
                onChange={e => setEntrance(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.floorLabel')}</Label>
              <Input
                type="number"
                value={floor}
                onChange={e => setFloor(e.target.value)}
              />
            </div>
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.roomsLabel')}</Label>
              <Input
                type="number"
                value={roomsCount}
                onChange={e => setRoomsCount(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.areaLabel')}</Label>
              <Input
                type="number"
                value={area}
                onChange={e => setArea(e.target.value)}
                step="0.1"
              />
            </div>
          </div>

          <div>
            <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.descriptionLabel')}</Label>
            <Textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>

          {mutation.error && (
            <div className="text-red text-[13px] font-[family-name:var(--font-display)]">
              {(mutation.error as any)?.response?.data?.detail || (mutation.error as Error).message || t('addressForms.saveError')}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={handleSubmit}
            disabled={mutation.isPending || !apartmentNumber.trim()}
          >
            {mutation.isPending ? t('common.saving') : apartment ? t('common.save') : t('common.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
