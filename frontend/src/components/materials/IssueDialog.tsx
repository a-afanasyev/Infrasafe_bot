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
import { Select } from '@/components/ui/select'
import { useCreateIssue } from '../../hooks/useMaterials'
import MaterialSelect from './MaterialSelect'

/**
 * Расход со склада: «по заявке» (request_number) или «хознужды» (reason).
 * doc_type явный — backend не выводит тип по полям (422 при несоответствии).
 */
export default function IssueDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const mutation = useCreateIssue()

  const [materialId, setMaterialId] = useState<number | ''>('')
  const [qty, setQty] = useState('')
  const [docType, setDocType] = useState<'request' | 'household'>('request')
  const [requestNumber, setRequestNumber] = useState('')
  const [reason, setReason] = useState('')

  // Render-time reset при открытии (паттерн ZoneFormDialog — без useEffect)
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setMaterialId('')
      setQty('')
      setDocType('request')
      setRequestNumber('')
      setReason('')
    }
  }

  const targetOk =
    docType === 'request' ? requestNumber.trim().length > 0 : reason.trim().length > 0
  const canSubmit = materialId !== '' && Number(qty) > 0 && targetOk && !mutation.isPending

  const submit = () =>
    mutation.mutate(
      {
        material_id: materialId as number,
        qty,
        doc_type: docType,
        request_number: docType === 'request' ? requestNumber.trim() : undefined,
        reason: docType === 'household' ? reason.trim() : undefined,
      },
      { onSuccess: onClose },
    )

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('materials.issue.title')}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.material')}</Label>
            <MaterialSelect value={materialId} onChange={setMaterialId} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.qty')}</Label>
            <Input type="number" min="0" step="0.001" value={qty}
                   onChange={(e) => setQty(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.issue.target')}</Label>
            <Select value={docType}
                    onChange={(e) => setDocType(e.target.value as 'request' | 'household')}>
              <option value="request">{t('materials.issue.byRequest')}</option>
              <option value="household">{t('materials.issue.household')}</option>
            </Select>
          </div>
          {docType === 'request' ? (
            <div className="flex flex-col gap-1.5">
              <Label>{t('materials.issue.requestNumber')}</Label>
              <Input
                placeholder="260705-001"
                value={requestNumber}
                onChange={(e) => setRequestNumber(e.target.value)}
              />
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label>{t('materials.form.reason')}</Label>
              <Input value={reason} onChange={(e) => setReason(e.target.value)} />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {mutation.isPending ? t('common.saving') : t('materials.issue.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
