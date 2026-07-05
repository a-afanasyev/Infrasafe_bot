import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useCreateAdjustment } from '../../hooks/useMaterials'
import MaterialSelect from './MaterialSelect'

/** Инвентаризационная корректировка: излишек (surplus) / недостача (shortage). */
export default function AdjustmentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const mutation = useCreateAdjustment()

  const [materialId, setMaterialId] = useState<number | ''>('')
  const [direction, setDirection] = useState<'surplus' | 'shortage'>('surplus')
  const [qty, setQty] = useState('')
  const [unitPrice, setUnitPrice] = useState('')
  const [reason, setReason] = useState('')

  // Render-time reset при открытии (паттерн ZoneFormDialog — без useEffect)
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setMaterialId('')
      setDirection('surplus')
      setQty('')
      setUnitPrice('')
      setReason('')
    }
  }

  const canSubmit =
    materialId !== '' && Number(qty) > 0 && reason.trim().length > 0 && !mutation.isPending

  const submit = () =>
    mutation.mutate(
      {
        material_id: materialId as number,
        direction,
        qty,
        unit_price: direction === 'surplus' && unitPrice !== '' ? unitPrice : undefined,
        reason: reason.trim(),
      },
      { onSuccess: onClose },
    )

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('materials.adjustment.title')}</DialogTitle>
          <DialogDescription>{t('materials.adjustment.subtitle')}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.material')}</Label>
            <MaterialSelect value={materialId} onChange={setMaterialId} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.adjustment.direction')}</Label>
            <Select value={direction}
                    onChange={(e) => setDirection(e.target.value as 'surplus' | 'shortage')}>
              <option value="surplus">{t('materials.adjustment.surplus')}</option>
              <option value="shortage">{t('materials.adjustment.shortage')}</option>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>{t('materials.form.qty')}</Label>
              <Input type="number" min="0" step="0.001" value={qty}
                     onChange={(e) => setQty(e.target.value)} />
            </div>
            {direction === 'surplus' && (
              <div className="flex flex-col gap-1.5">
                <Label>{t('materials.receipt.unitPrice')}</Label>
                <Input type="number" min="0" step="0.01" value={unitPrice}
                       onChange={(e) => setUnitPrice(e.target.value)} />
              </div>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.reason')}</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {mutation.isPending ? t('common.saving') : t('materials.adjustment.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
