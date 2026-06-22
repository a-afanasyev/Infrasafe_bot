import { useTranslation } from 'react-i18next'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog"
import { cn } from "@/lib/utils"

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: "danger" | "warning" | "default"
  onConfirm: () => void
  loading?: boolean
  /**
   * Закрыть диалог сразу после onConfirm (по умолчанию true).
   * Диалог контролируемый (`open` приходит из родителя), поэтому встроенный
   * close Radix перебивается ре-рендером, если onConfirm синхронно мутирует
   * состояние — диалог «зависал» открытым после успешного действия. Явный
   * onOpenChange(false) это чинит для fire-and-forget вызывателей.
   * Async-flow, которые сами закрывают родителя после await, ставят false.
   */
  closeOnConfirm?: boolean
}

const variantStyles = {
  danger: "bg-red text-white hover:bg-red/90",
  warning: "bg-amber text-white hover:bg-amber/90",
  default: "bg-accent text-white hover:bg-accent/90",
} as const

export default function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel,
  variant = "danger",
  onConfirm,
  loading = false,
  closeOnConfirm = true,
}: ConfirmDialogProps) {
  const { t } = useTranslation()
  const resolvedConfirmLabel = confirmLabel ?? t('common.delete')
  const resolvedCancelLabel = cancelLabel ?? t('common.cancel')

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={loading}>
            {resolvedCancelLabel}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={() => {
              onConfirm()
              if (closeOnConfirm) onOpenChange(false)
            }}
            disabled={loading}
            className={cn(variantStyles[variant], loading && "opacity-70")}
          >
            {loading ? t('errors.executing') : resolvedConfirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
