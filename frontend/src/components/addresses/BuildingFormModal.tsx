import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useCreateBuilding, useUpdateBuilding } from '../../hooks/useAddresses'
import type { BuildingBrief, YardBrief } from '../../types/api'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { safeErrorMessage } from '@/utils/errorMessage'

interface Props {
  building?: BuildingBrief
  yardId: number
  yards: YardBrief[]
  onClose: () => void
}

export default function BuildingFormModal({ building, yardId, yards, onClose }: Props) {
  const { t } = useTranslation()
  const [selectedYardId, setSelectedYardId] = useState(building?.yard_id ?? yardId)
  const [address, setAddress] = useState(building?.address ?? '')
  const [entranceCount, setEntranceCount] = useState(building?.entrance_count ?? 1)
  const [floorCount, setFloorCount] = useState(building?.floor_count ?? 1)
  const [description, setDescription] = useState(building?.description ?? '')
  const [gpsLat, setGpsLat] = useState<string>(building?.gps_latitude != null ? String(building.gps_latitude) : '')
  const [gpsLon, setGpsLon] = useState<string>(building?.gps_longitude != null ? String(building.gps_longitude) : '')

  const createBuilding = useCreateBuilding()
  const updateBuilding = useUpdateBuilding()
  const mutation = building ? updateBuilding : createBuilding

  const handleSubmit = () => {
    if (!address.trim()) return

    const lat = gpsLat ? parseFloat(gpsLat) : null
    const lon = gpsLon ? parseFloat(gpsLon) : null

    if (lat != null && (isNaN(lat) || lat < -90 || lat > 90)) return
    if (lon != null && (isNaN(lon) || lon < -180 || lon > 180)) return

    const payload = {
      address: address.trim(),
      yard_id: selectedYardId,
      entrance_count: entranceCount,
      floor_count: floorCount,
      description: description.trim() || null,
      gps_latitude: lat,
      gps_longitude: lon,
    }

    if (building) {
      updateBuilding.mutate(
        { id: building.id, ...payload },
        { onSuccess: onClose },
      )
    } else {
      createBuilding.mutate(
        { ...payload, is_active: true },
        { onSuccess: onClose },
      )
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{building ? t('addressForms.editBuilding') : t('addressForms.newBuilding')}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div>
            <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.yardRequired')}</Label>
            <Select
              value={selectedYardId}
              onChange={e => setSelectedYardId(Number(e.target.value))}
            >
              {yards.map(y => (
                <option key={y.id} value={y.id}>{y.name}</option>
              ))}
            </Select>
          </div>

          <div>
            <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.addressLabel')}</Label>
            <Input
              value={address}
              onChange={e => setAddress(e.target.value)}
              autoFocus
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.entrancesLabel')}</Label>
              <Input
                type="number"
                value={entranceCount}
                onChange={e => setEntranceCount(Math.max(1, parseInt(e.target.value) || 1))}
                min={1}
              />
            </div>
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.floorsLabel')}</Label>
              <Input
                type="number"
                value={floorCount}
                onChange={e => setFloorCount(Math.max(1, parseInt(e.target.value) || 1))}
                min={1}
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

          <div className="flex gap-3">
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.gpsLat')}</Label>
              <Input
                type="number"
                min={-90}
                max={90}
                step="any"
                value={gpsLat}
                onChange={e => setGpsLat(e.target.value)}
                placeholder="-90 ... 90"
              />
            </div>
            <div className="flex-1">
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.gpsLon')}</Label>
              <Input
                type="number"
                min={-180}
                max={180}
                step="any"
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
            disabled={mutation.isPending || !address.trim()}
          >
            {mutation.isPending ? t('common.saving') : building ? t('common.save') : t('common.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
