import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useCreateYard, useCreateBuilding } from '../../hooks/useAddresses'
import { safeErrorMessage } from '@/utils/errorMessage'
import type { YardBrief } from '../../types/api'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type ObjectType = 'yard' | 'building' | null

interface Props {
  open: boolean
  onClose: () => void
  yards: YardBrief[]
  preselectedYardId?: number
}

export default function AddObjectModal({ open, onClose, yards, preselectedYardId }: Props) {
  const { t } = useTranslation()
  const [objectType, setObjectType] = useState<ObjectType>(null)

  // Yard fields
  const [yardName, setYardName] = useState('')
  const [yardDescription, setYardDescription] = useState('')
  const [yardLat, setYardLat] = useState('')
  const [yardLon, setYardLon] = useState('')

  // Building fields
  const [selectedYardId, setSelectedYardId] = useState<number>(0)
  const [address, setAddress] = useState('')
  const [entranceCount, setEntranceCount] = useState(1)
  const [floorCount, setFloorCount] = useState(1)
  const [buildingDescription, setBuildingDescription] = useState('')
  const [buildingLat, setBuildingLat] = useState('')
  const [buildingLon, setBuildingLon] = useState('')

  const createYard = useCreateYard()
  const createBuilding = useCreateBuilding()

  // Reset when opening/closing
  useEffect(() => {
    if (open) {
      if (preselectedYardId) {
        setObjectType('building')
        setSelectedYardId(preselectedYardId)
      } else {
        setObjectType(null)
        setSelectedYardId(yards[0]?.id ?? 0)
      }
      setYardName('')
      setYardDescription('')
      setYardLat('')
      setYardLon('')
      setAddress('')
      setEntranceCount(1)
      setFloorCount(1)
      setBuildingDescription('')
      setBuildingLat('')
      setBuildingLon('')
    }
  }, [open, preselectedYardId, yards])

  const handleSubmitYard = () => {
    if (!yardName.trim()) return
    const lat = yardLat ? parseFloat(yardLat) : null
    const lon = yardLon ? parseFloat(yardLon) : null
    if (lat != null && (isNaN(lat) || lat < -90 || lat > 90)) return
    if (lon != null && (isNaN(lon) || lon < -180 || lon > 180)) return

    createYard.mutate(
      { name: yardName.trim(), description: yardDescription.trim() || null, gps_latitude: lat, gps_longitude: lon, is_active: true },
      { onSuccess: onClose },
    )
  }

  const handleSubmitBuilding = () => {
    if (!address.trim() || !selectedYardId) return
    const lat = buildingLat ? parseFloat(buildingLat) : null
    const lon = buildingLon ? parseFloat(buildingLon) : null
    if (lat != null && (isNaN(lat) || lat < -90 || lat > 90)) return
    if (lon != null && (isNaN(lon) || lon < -180 || lon > 180)) return

    createBuilding.mutate(
      {
        address: address.trim(),
        yard_id: selectedYardId,
        entrance_count: entranceCount,
        floor_count: floorCount,
        description: buildingDescription.trim() || null,
        gps_latitude: lat,
        gps_longitude: lon,
        is_active: true,
      },
      { onSuccess: onClose },
    )
  }

  const mutation = objectType === 'yard' ? createYard : objectType === 'building' ? createBuilding : null
  const canSubmit = objectType === 'yard' ? yardName.trim() : objectType === 'building' ? address.trim() && selectedYardId : false

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>
            {objectType === null ? t('addressForms.newObject') : objectType === 'yard' ? t('addressForms.newYard') : t('addressForms.newBuilding')}
          </DialogTitle>
        </DialogHeader>

        {/* Step 1: Choose type */}
        {objectType === null && (
          <div className="flex gap-3">
            <button
              onClick={() => setObjectType('yard')}
              className={cn(
                'flex-1 flex flex-col items-center gap-2 p-6 rounded-lg border-2 border-border-default',
                'bg-bg-surface cursor-pointer transition-all',
                'hover:border-accent hover:shadow-[0_0_0_1px_var(--accent)]'
              )}
            >
              <span className="text-3xl">{'\u{1F3D8}'}</span>
              <span className="text-sm font-semibold font-[family-name:var(--font-display)] text-text-primary">{t('addressForms.yardLabel')}</span>
            </button>
            <button
              onClick={() => {
                setObjectType('building')
                setSelectedYardId(yards[0]?.id ?? 0)
              }}
              className={cn(
                'flex-1 flex flex-col items-center gap-2 p-6 rounded-lg border-2 border-border-default',
                'bg-bg-surface cursor-pointer transition-all',
                'hover:border-accent hover:shadow-[0_0_0_1px_var(--accent)]'
              )}
            >
              <span className="text-3xl">{'\u{1F3E2}'}</span>
              <span className="text-sm font-semibold font-[family-name:var(--font-display)] text-text-primary">{t('addressForms.buildingLabel')}</span>
            </button>
          </div>
        )}

        {/* Step 2: Yard form */}
        {objectType === 'yard' && (
          <div className="flex flex-col gap-4">
            {!preselectedYardId && (
              <button
                onClick={() => setObjectType(null)}
                className="self-start text-xs text-accent cursor-pointer bg-transparent border-none font-[family-name:var(--font-display)] hover:underline"
              >
                &larr; {t('addressForms.chooseType')}
              </button>
            )}
            <div>
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.nameLabel')}</Label>
              <Input value={yardName} onChange={e => setYardName(e.target.value)} autoFocus />
            </div>
            <div>
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.descriptionLabel')}</Label>
              <Textarea value={yardDescription} onChange={e => setYardDescription(e.target.value)} />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.gpsLat')}</Label>
                <Input type="number" min={-90} max={90} step="any" value={yardLat} onChange={e => setYardLat(e.target.value)} placeholder="-90 ... 90" />
              </div>
              <div className="flex-1">
                <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.gpsLon')}</Label>
                <Input type="number" min={-180} max={180} step="any" value={yardLon} onChange={e => setYardLon(e.target.value)} placeholder="-180 ... 180" />
              </div>
            </div>
            {createYard.error && (
              <div className="text-red text-[13px] font-[family-name:var(--font-display)]">
                {safeErrorMessage(createYard.error, t('addressForms.saveError'))}
              </div>
            )}
          </div>
        )}

        {/* Step 2: Building form */}
        {objectType === 'building' && (
          <div className="flex flex-col gap-4">
            {!preselectedYardId && (
              <button
                onClick={() => setObjectType(null)}
                className="self-start text-xs text-accent cursor-pointer bg-transparent border-none font-[family-name:var(--font-display)] hover:underline"
              >
                &larr; {t('addressForms.chooseType')}
              </button>
            )}
            <div>
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.yardRequired')}</Label>
              <Select value={selectedYardId} onChange={e => setSelectedYardId(Number(e.target.value))}>
                {yards.map(y => (
                  <option key={y.id} value={y.id}>{y.name}</option>
                ))}
              </Select>
            </div>
            <div>
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.addressLabel')}</Label>
              <Input value={address} onChange={e => setAddress(e.target.value)} autoFocus />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.entrancesLabel')}</Label>
                <Input type="number" value={entranceCount} onChange={e => setEntranceCount(Math.max(1, parseInt(e.target.value) || 1))} min={1} />
              </div>
              <div className="flex-1">
                <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.floorsLabel')}</Label>
                <Input type="number" value={floorCount} onChange={e => setFloorCount(Math.max(1, parseInt(e.target.value) || 1))} min={1} />
              </div>
            </div>
            <div>
              <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.descriptionLabel')}</Label>
              <Textarea value={buildingDescription} onChange={e => setBuildingDescription(e.target.value)} />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.gpsLat')}</Label>
                <Input type="number" min={-90} max={90} step="any" value={buildingLat} onChange={e => setBuildingLat(e.target.value)} placeholder="-90 ... 90" />
              </div>
              <div className="flex-1">
                <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.gpsLon')}</Label>
                <Input type="number" min={-180} max={180} step="any" value={buildingLon} onChange={e => setBuildingLon(e.target.value)} placeholder="-180 ... 180" />
              </div>
            </div>
            {createBuilding.error && (
              <div className="text-red text-[13px] font-[family-name:var(--font-display)]">
                {safeErrorMessage(createBuilding.error, t('addressForms.saveError'))}
              </div>
            )}
          </div>
        )}

        {/* Footer — only show when a type is selected */}
        {objectType !== null && (
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
            <Button
              onClick={objectType === 'yard' ? handleSubmitYard : handleSubmitBuilding}
              disabled={mutation?.isPending || !canSubmit}
            >
              {mutation?.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
