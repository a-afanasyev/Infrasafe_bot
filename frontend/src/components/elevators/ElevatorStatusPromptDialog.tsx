import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ElevatorStatusDot } from './ElevatorStatusBadge'
import { buildStatusReason } from './statusReason'
import { elevatorKeys, useSetElevatorStatus } from '../../hooks/useElevators'
import { ELEVATOR_STATUSES, type ElevatorStatus } from '../../types/elevators'

/**
 * Подсказка менеджеру после подтверждения заявки по лифту: «Лифт {label}:
 * сейчас «{статус}». Лифт работает?» — четыре статуса + «Оставить как есть».
 * Выбор → PUT /elevators/{id}/status с reason (statusReason.ts, ≤ 500) и
 * request_number (при одной заявке); toast и инвалидацию реестра/карточки/
 * канбана делает useSetElevatorStatus, заявки — этот диалог. Тот же статус,
 * что и текущий, — «без изменений» без запроса.
 */
interface Props {
  open: boolean
  elevatorId: number
  elevatorLabel: string
  currentStatus: ElevatorStatus | null
  requestNumbers: readonly string[]
  onClose: () => void
}

/** Префикс кэша карточек заявок (`['request', number]`). */
const REQUEST_QUERY_PREFIX = ['request'] as const

export default function ElevatorStatusPromptDialog({
  open, elevatorId, elevatorLabel, currentStatus, requestNumbers, onClose,
}: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const mutation = useSetElevatorStatus(elevatorId)

  const choose = (status: ElevatorStatus) => {
    if (status === currentStatus) {
      toast.info(t('elevators.toast.statusUnchanged'))
      onClose()
      return
    }
    mutation.mutate(
      {
        status,
        reason: buildStatusReason(t, requestNumbers),
        request_number: requestNumbers.length === 1 ? requestNumbers[0] : null,
      },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: elevatorKeys.requests(elevatorId) })
          queryClient.invalidateQueries({ queryKey: REQUEST_QUERY_PREFIX })
          onClose()
        },
      },
    )
  }

  const statusText = t(currentStatus ? `elevators.status.${currentStatus}` : 'elevators.status.none')

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('elevators.prompt.title')}</DialogTitle>
        </DialogHeader>
        <p className="text-[13px] text-text-secondary">
          {t('elevators.prompt.body', { label: elevatorLabel, status: statusText })}
        </p>
        <div className="grid grid-cols-2 gap-2">
          {ELEVATOR_STATUSES.map((status) => (
            <Button
              key={status}
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => choose(status)}
              className={cn('justify-start gap-2', status === currentStatus && 'border-accent')}
            >
              <ElevatorStatusDot status={status} />
              <span>{t(`elevators.status.${status}`)}</span>
              {status === currentStatus && (
                <span className="text-text-muted text-[11px]">· {t('elevators.prompt.current')}</span>
              )}
            </Button>
          ))}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
            {t('elevators.prompt.keep')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
