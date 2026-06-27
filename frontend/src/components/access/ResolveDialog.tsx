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
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/**
 * Диалог резолюции события manual_review охранником: ввод причины (reason) +
 * подтверждение действия (открыть / отказать). Причина обязательна (бэкенд
 * требует non-empty reason, §9.5).
 *
 * Для action=manual_open бэкенд также требует barrier_id (шлагбаум принадлежит
 * точке проезда — у одной gate может быть несколько barriers, §5.2). В реестре
 * событий barrier_id нет, поэтому оператор подтверждает его в диалоге;
 * предзаполняем gate_id как подсказку (в пилотной 1-к-1 раскладке совпадает).
 */
export interface ResolveTarget {
  action: 'manual_open' | 'deny'
  /** Подсказка для предзаполнения barrier_id (gate_id события). */
  defaultBarrierId?: number | null
}

export interface ResolveSubmit {
  reason: string
  barrierId?: number
}

interface Props {
  target: ResolveTarget | null
  loading?: boolean
  onClose: () => void
  onSubmit: (data: ResolveSubmit) => void
}

export default function ResolveDialog({ target, loading, onClose, onSubmit }: Props) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  const [barrierId, setBarrierId] = useState('')

  // Сброс полей при смене target (открытие нового события) — render-time pattern
  // React (adjusting state during render), не effect: иначе текст «перетекал» бы
  // между событиями, а setState-в-effect ругается линтером.
  const [prevTarget, setPrevTarget] = useState<ResolveTarget | null>(null)
  if (target !== prevTarget) {
    setPrevTarget(target)
    if (target) {
      setReason('')
      setBarrierId(target.defaultBarrierId != null ? String(target.defaultBarrierId) : '')
    }
  }

  const isOpen = target !== null
  const isManualOpen = target?.action === 'manual_open'
  const barrierOk = !isManualOpen || barrierId.trim().length > 0
  const canSubmit = reason.trim().length > 0 && barrierOk && !loading

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isManualOpen
              ? t('accessControl.resolve.openTitle')
              : t('accessControl.resolve.denyTitle')}
          </DialogTitle>
          <DialogDescription>
            {isManualOpen
              ? t('accessControl.resolve.openDesc')
              : t('accessControl.resolve.denyDesc')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          {isManualOpen && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="resolve-barrier">{t('accessControl.resolve.barrierLabel')}</Label>
              <Input
                id="resolve-barrier"
                type="number"
                value={barrierId}
                onChange={(e) => setBarrierId(e.target.value)}
                placeholder={t('accessControl.resolve.barrierPlaceholder')}
              />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="resolve-reason">{t('accessControl.resolve.reasonLabel')}</Label>
            <Textarea
              id="resolve-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t('accessControl.resolve.reasonPlaceholder')}
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={isManualOpen ? 'default' : 'destructive'}
            disabled={!canSubmit}
            onClick={() =>
              onSubmit({
                reason: reason.trim(),
                barrierId: isManualOpen ? Number(barrierId) : undefined,
              })
            }
          >
            {isManualOpen
              ? t('accessControl.resolve.openConfirm')
              : t('accessControl.resolve.denyConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
