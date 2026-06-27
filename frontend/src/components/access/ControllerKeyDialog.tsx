import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Copy, Check, KeyRound, AlertTriangle } from 'lucide-react'
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
 * Модалка показа API-ключа контроллера. Ключ отдаётся бэкендом в открытом виде
 * РОВНО ОДИН РАЗ (при создании и при ротации) и больше нигде не доступен —
 * поэтому: моноширинный вывод, кнопка «Скопировать» и явное предупреждение
 * «сохраните — больше не покажем». Закрытие модалки = ключ потерян безвозвратно.
 */
interface Props {
  /** controller_uid, к которому относится ключ (для контекста). */
  controllerUid: string | null
  /** Сам ключ (PLAINTEXT). null → модалка закрыта. */
  apiKey: string | null
  onClose: () => void
}

export default function ControllerKeyDialog({ controllerUid, apiKey, onClose }: Props) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const open = apiKey !== null

  async function copy() {
    if (!apiKey) return
    try {
      await navigator.clipboard.writeText(apiKey)
      setCopied(true)
      toast.success(t('accessControl.equipment.key.copied'))
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('common.error'))
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          setCopied(false)
          onClose()
        }
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound size={18} className="text-accent" />
            {t('accessControl.equipment.key.title')}
          </DialogTitle>
          <DialogDescription>
            {t('accessControl.equipment.key.subtitle', { uid: controllerUid ?? '' })}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex items-start gap-2 rounded-default border border-amber-300 bg-amber-50 p-3 text-[12px] text-amber-800 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-300">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span>{t('accessControl.equipment.key.warning')}</span>
          </div>

          <div className="flex items-center gap-2">
            <code className="flex-1 overflow-x-auto rounded-sm border border-border-default bg-bg-surface px-3 py-2 font-mono text-[13px] text-text-primary">
              {apiKey}
            </code>
            <Button variant="outline" size="icon" onClick={copy} aria-label={t('accessControl.equipment.key.copy')}>
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={onClose}>{t('accessControl.equipment.key.done')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
