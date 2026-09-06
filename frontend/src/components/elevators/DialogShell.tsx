import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'

/**
 * Общий каркас диалогов модуля «Лифты»: заголовок, тело, Отмена/Действие.
 * `submitVariant="destructive"` — для архивации.
 */
interface ShellProps {
  open: boolean
  title: string
  onClose: () => void
  onSubmit: () => void
  canSubmit: boolean
  pending: boolean
  submitLabel: string
  pendingLabel?: string
  submitVariant?: 'default' | 'destructive'
  children: React.ReactNode
}

export function DialogShell({
  open, title, onClose, onSubmit, canSubmit, pending, submitLabel, pendingLabel, submitVariant = 'default', children,
}: ShellProps) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">{children}</div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={pending}>{t('common.cancel')}</Button>
          <Button variant={submitVariant} onClick={onSubmit} disabled={!canSubmit || pending}>
            {pending ? (pendingLabel ?? t('common.saving')) : submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Подпись + контрол (id связывает Label с инпутом — важно для a11y и тестов). */
export function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  )
}
