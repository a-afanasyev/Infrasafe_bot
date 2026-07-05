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
import { useCreateAdjustment } from '../../hooks/useMaterials'
import { fmtQty } from '../../utils/materialsFormat'
import { useUnitLabel } from '../../hooks/useUnitLabel'
import type { OperationRow } from '../../types/materials'

/**
 * Сторно операции из журнала (кнопка на строке). Полное и однократное:
 * qty не передаётся — объём берёт backend из исходной операции.
 * Сторно расхода → surplus-партии по исходным ценам; сторно прихода —
 * только для нетронутой партии (иначе 409).
 */
interface Props {
  operation: OperationRow | null
  onClose: () => void
}

export default function ReversalDialog({ operation, onClose }: Props) {
  const { t } = useTranslation()
  const unitLabel = useUnitLabel()
  const mutation = useCreateAdjustment()
  const [reason, setReason] = useState('')

  // Render-time reset при смене сторнируемой операции (без useEffect)
  const [prevOperation, setPrevOperation] = useState<OperationRow | null>(null)
  if (operation !== prevOperation) {
    setPrevOperation(operation)
    setReason('')
  }

  if (!operation) return null

  const isIssue = operation.op_type === 'issue'
  const canSubmit = reason.trim().length > 0 && !mutation.isPending

  const submit = () =>
    mutation.mutate(
      {
        material_id: operation.material_id,
        direction: isIssue ? 'surplus' : 'shortage',
        reason: reason.trim(),
        ...(isIssue
          ? { reversal_of_issue_id: operation.id }
          : { reversal_of_receipt_id: operation.id }),
      },
      { onSuccess: onClose },
    )

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>
            {isIssue ? t('materials.reversal.issueTitle') : t('materials.reversal.receiptTitle')}
          </DialogTitle>
          <DialogDescription>
            {t('materials.reversal.summary', {
              name: operation.material_name,
              qty: fmtQty(operation.qty),
              unit: unitLabel(operation.unit),
            })}{' '}
            {isIssue ? t('materials.reversal.issueHint') : t('materials.reversal.receiptHint')}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label>{t('materials.form.reason')}</Label>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button variant="destructive" onClick={submit} disabled={!canSubmit}>
            {mutation.isPending ? t('common.saving') : t('materials.reversal.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
