import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCreateReceipt } from '../../hooks/useMaterials'
import MaterialSelect from './MaterialSelect'

/** Приход (закупка): создаёт партию FIFO — кол-во × цена + документ/поставщик. */
export default function ReceiptDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const mutation = useCreateReceipt()

  const [materialId, setMaterialId] = useState<number | ''>('')
  const [qty, setQty] = useState('')
  const [unitPrice, setUnitPrice] = useState('')
  const [supplier, setSupplier] = useState('')
  const [docNumber, setDocNumber] = useState('')
  const [docDate, setDocDate] = useState('')
  const [note, setNote] = useState('')

  // Render-time reset при открытии (паттерн ZoneFormDialog — без useEffect)
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setMaterialId('')
      setQty('')
      setUnitPrice('')
      setSupplier('')
      setDocNumber('')
      setDocDate('')
      setNote('')
    }
  }

  const canSubmit =
    materialId !== '' && Number(qty) > 0 && Number(unitPrice) >= 0 && !mutation.isPending

  const submit = () =>
    mutation.mutate(
      {
        material_id: materialId as number,
        qty,
        unit_price: unitPrice,
        supplier: supplier.trim() || undefined,
        doc_number: docNumber.trim() || undefined,
        doc_date: docDate || undefined,
        note: note.trim() || undefined,
      },
      { onSuccess: onClose },
    )

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('materials.receipt.title')}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.material')}</Label>
            <MaterialSelect value={materialId} onChange={setMaterialId} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>{t('materials.form.qty')}</Label>
              <Input type="number" min="0" step="0.001" value={qty}
                     onChange={(e) => setQty(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>{t('materials.receipt.unitPrice')}</Label>
              <Input type="number" min="0" step="0.01" value={unitPrice}
                     onChange={(e) => setUnitPrice(e.target.value)} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.receipt.supplier')}</Label>
            <Input value={supplier} onChange={(e) => setSupplier(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>{t('materials.receipt.docNumber')}</Label>
              <Input value={docNumber} onChange={(e) => setDocNumber(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>{t('materials.receipt.docDate')}</Label>
              <Input type="date" value={docDate} onChange={(e) => setDocDate(e.target.value)} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.note')}</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {mutation.isPending ? t('common.saving') : t('materials.receipt.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
