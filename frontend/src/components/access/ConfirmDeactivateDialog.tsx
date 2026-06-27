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

/**
 * Подтверждение деактивации элемента оборудования (PATCH is_active=false).
 * `label` — отображаемое имя/код деактивируемого объекта (для текста подтверждения).
 */
interface Props {
  open: boolean
  label: string
  loading?: boolean
  onClose: () => void
  onConfirm: () => void
  /** Переопределение заголовка/текста/кнопки (повторно используется для ротации ключа). */
  title?: string
  message?: string
  confirmLabel?: string
}

export default function ConfirmDeactivateDialog({
  open,
  label,
  loading,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel,
}: Props) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title ?? t('accessControl.equipment.deactivateTitle')}</DialogTitle>
          <DialogDescription>
            {message ?? t('accessControl.equipment.deactivateConfirm', { name: label })}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button variant="destructive" disabled={loading} onClick={onConfirm}>
            {loading ? t('common.saving') : confirmLabel ?? t('accessControl.equipment.deactivate')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
