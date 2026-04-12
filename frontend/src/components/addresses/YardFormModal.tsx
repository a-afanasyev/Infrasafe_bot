import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useCreateYard, useUpdateYard } from '../../hooks/useAddresses'
import type { YardBrief } from '../../types/api'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { safeErrorMessage } from '@/utils/errorMessage'

interface Props {
  yard?: YardBrief
  onClose: () => void
}

export default function YardFormModal({ yard, onClose }: Props) {
  const { t } = useTranslation()
  const [name, setName] = useState(yard?.name ?? '')
  const [description, setDescription] = useState(yard?.description ?? '')
  const [gpsLat, setGpsLat] = useState<string>(yard?.gps_latitude != null ? String(yard.gps_latitude) : '')
  const [gpsLon, setGpsLon] = useState<string>(yard?.gps_longitude != null ? String(yard.gps_longitude) : '')

  const createYard = useCreateYard()
  const updateYard = useUpdateYard()
  const mutation = yard ? updateYard : createYard

  const handleSubmit = () => {
    if (!name.trim()) return

    const lat = gpsLat ? parseFloat(gpsLat) : null
    const lon = gpsLon ? parseFloat(gpsLon) : null

    if (lat != null && (isNaN(lat) || lat < -90 || lat > 90)) return
    if (lon != null && (isNaN(lon) || lon < -180 || lon > 180)) return

    if (yard) {
      updateYard.mutate(
        { id: yard.id, name: name.trim(), description: description.trim() || null, gps_latitude: lat, gps_longitude: lon },
        { onSuccess: onClose },
      )
    } else {
      createYard.mutate(
        { name: name.trim(), description: description.trim() || null, gps_latitude: lat, gps_longitude: lon, is_active: true },
        { onSuccess: onClose },
      )
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{yard ? t('addressForms.editYard') : t('addressForms.newYard')}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div>
            <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.nameLabel')}</Label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              autoFocus
            />
          </div>

          <div>
            <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.descriptionLabel')}</Label>
            <Textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.gpsLat')}</Label>
              <Input
                type="number"
                value={gpsLat}
                onChange={e => setGpsLat(e.target.value)}
                placeholder="-90 ... 90"
              />
            </div>
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.gpsLon')}</Label>
              <Input
                type="number"
                value={gpsLon}
                onChange={e => setGpsLon(e.target.value)}
                placeholder="-180 ... 180"
              />
            </div>
          </div>

          {mutation.error && (
            <div className="text-red text-[13px] font-[family-name:var(--font-display)]">
              {safeErrorMessage(mutation.error, t('addressForms.saveError'))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={handleSubmit}
            disabled={mutation.isPending || !name.trim()}
          >
            {mutation.isPending ? t('common.saving') : yard ? t('common.save') : t('common.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
