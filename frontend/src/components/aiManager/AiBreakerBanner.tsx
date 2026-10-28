import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { AiBreakerStatus } from '../../types/autoManagerConfig'

// Предохранитель ИИ-триажа: открыт → жёлтая плашка с кнопкой сброса;
// закрыт → строка со счётчиком; null → Redis недоступен.
interface AiBreakerBannerProps {
  status: AiBreakerStatus | null
  pending: boolean
  onReset: () => void
}

export default function AiBreakerBanner({ status, pending, onReset }: AiBreakerBannerProps) {
  const { t } = useTranslation()
  if (status === null) {
    return <p className="text-[11px] text-text-muted">{t('aiManager.breaker.unknown')}</p>
  }
  if (!status.open) {
    return <p className="text-[11px] text-text-muted">{t('aiManager.breaker.closed', { failures: status.failures })}</p>
  }
  return (
    <div className={cn('flex flex-wrap items-center justify-between gap-2 rounded-default border p-3 text-[12px]',
      'border-amber-500/50 bg-amber-500/10 text-text-primary')}>
      <span>{t('aiManager.breaker.open', { minutes: Math.ceil(status.open_ttl / 60), failures: status.failures })}</span>
      <Button size="sm" variant="outline" disabled={pending} onClick={onReset}>{t('aiManager.breaker.reset')}</Button>
    </div>
  )
}
