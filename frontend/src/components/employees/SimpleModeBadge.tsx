import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

/** Бейдж «Простой режим»: поддержка сразу видит, какая панель у человека в Mini App. */
export default function SimpleModeBadge({ className }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <span
      data-testid="simple-mode-badge"
      className={cn('font-semibold rounded-[10px] bg-accent/15 text-accent', className)}
    >
      {t('employees.simpleModeBadge')}
    </span>
  )
}
