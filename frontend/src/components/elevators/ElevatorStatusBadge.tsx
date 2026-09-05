import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { ElevatorStatus } from '../../types/elevators'

/**
 * Бейдж статуса лифта: working зелёный, not_working красный, under_repair
 * оранжевый, maintenance синий, null серый «не введён».
 */
const STATUS_CLASS: Record<ElevatorStatus, string> = {
  working: 'bg-green/15 text-green',
  not_working: 'bg-red/15 text-red',
  under_repair: 'bg-orange/15 text-orange',
  maintenance: 'bg-blue/15 text-blue',
}

export default function ElevatorStatusBadge({ status }: { status: ElevatorStatus | null }) {
  const { t } = useTranslation()
  return (
    <span
      className={cn(
        'inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold whitespace-nowrap',
        status ? STATUS_CLASS[status] : 'bg-bg-surface text-text-muted',
      )}
    >
      {t(status ? `elevators.status.${status}` : 'elevators.status.none')}
    </span>
  )
}
