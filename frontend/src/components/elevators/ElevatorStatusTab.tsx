import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import ElevatorStatusBadge from './ElevatorStatusBadge'
import StatusChangeDialog from './StatusChangeDialog'
import { fmtAvailability, fmtInstant } from '../../utils/elevatorsFormat'
import { ELEVATOR_STATUSES, type ElevatorDetail, type ElevatorStatus } from '../../types/elevators'

/**
 * Вкладка «Статус»: текущий статус, с какого времени, доступность 30д и
 * четыре кнопки статусов → диалог с причиной. Недоступно, если лифт не введён
 * в эксплуатацию или в архиве. Смена статуса разрешена executor и manager.
 */
export default function ElevatorStatusTab({ elevator }: { elevator: ElevatorDetail }) {
  const { t } = useTranslation()
  const [target, setTarget] = useState<ElevatorStatus | null>(null)
  const locked = !elevator.is_commissioned || elevator.archived_at !== null

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-bg-card border border-border-default rounded-default p-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider text-text-muted">{t('elevators.detail.currentStatus')}</span>
          <ElevatorStatusBadge status={elevator.current_status} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider text-text-muted">{t('elevators.detail.since')}</span>
          <span className="text-[13px] text-text-primary">{fmtInstant(elevator.status_since)}</span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider text-text-muted">{t('elevators.detail.availability')}</span>
          <span className="text-[13px] text-text-primary">{fmtAvailability(elevator.availability_30d)}</span>
        </div>
      </div>

      {!elevator.is_commissioned && (
        <p className="text-[13px] text-text-muted">{t('elevators.detail.statusNeedsCommission')}</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {ELEVATOR_STATUSES.map((s) => (
          <Button
            key={s}
            size="sm"
            variant={elevator.current_status === s ? 'default' : 'outline'}
            disabled={locked || elevator.current_status === s}
            onClick={() => setTarget(s)}
          >
            {t(`elevators.status.${s}`)}
          </Button>
        ))}
      </div>

      <StatusChangeDialog elevatorId={elevator.id} status={target} onClose={() => setTarget(null)} />
    </div>
  )
}
