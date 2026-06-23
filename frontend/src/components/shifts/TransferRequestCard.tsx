import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useHandleTransfer } from '../../hooks/useShifts'
import { useEmployees } from '../../hooks/useEmployees'
import { useHasRole } from '../../hooks/useHasRole'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { TransferOut } from '../../types/api'

interface Props {
  transfer: TransferOut
}

const URGENCY_DOT: Record<string, string> = {
  critical: 'bg-red',
  high: 'bg-amber',
}

/**
 * Карточка запроса на передачу смены с менеджерскими действиями.
 * Список `/shifts/transfers` отдаёт только pending/assigned, поэтому:
 *  - pending  → «Назначить исполнителя» (approve + picker) / «Отменить» (cancel)
 *  - assigned → «Отклонить» (reject) / «Отменить» (cancel)
 * Все действия идут через POST /shifts/transfers/{id}/handle (useHandleTransfer).
 */
export default function TransferRequestCard({ transfer }: Props) {
  const { t } = useTranslation()
  const handle = useHandleTransfer()
  const isManager = useHasRole('manager')
  const [assigning, setAssigning] = useState(false)
  const [picked, setPicked] = useState('')
  const { data: employees } = useEmployees({}, undefined)

  // Approve требует executor-роль; исключаем инициатора (по имени — id в
  // TransferOut нет) и берём только approved.
  const eligible = (employees ?? []).filter(
    e =>
      e.status === 'approved' &&
      [e.first_name, e.last_name].filter(Boolean).join(' ').trim() !== transfer.from_executor_name,
  )

  const run = async (action: 'approve' | 'reject' | 'cancel', toExecutorId?: number) => {
    try {
      await handle.mutateAsync({ id: transfer.id, action, to_executor_id: toExecutorId })
      setAssigning(false)
      setPicked('')
    } catch {
      // ошибка показывается тостом внутри useHandleTransfer
    }
  }

  return (
    <div className="flex flex-col gap-2 p-2.5 bg-bg-surface rounded-sm">
      <div className="flex items-start gap-2">
        <div
          className={cn(
            'w-2 h-2 rounded-full mt-1 shrink-0',
            URGENCY_DOT[transfer.urgency_level] ?? 'bg-blue',
          )}
        />
        <div className="flex-1 overflow-hidden">
          <div className="text-xs text-text-primary font-semibold truncate">
            {transfer.from_executor_name} → {transfer.to_executor_name ?? '?'}
          </div>
          <div className="text-[11px] text-text-muted mt-0.5">
            {t(`transferReason.${transfer.reason}`, transfer.reason)}
          </div>
        </div>
      </div>

      {isManager && (
        <>
          {!assigning && (
            <div className="flex gap-1.5 flex-wrap">
              {transfer.status === 'pending' && (
                <Button size="sm" onClick={() => setAssigning(true)} disabled={handle.isPending}>
                  {t('shifts.transferAssign')}
                </Button>
              )}
              {transfer.status === 'assigned' && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => run('reject')}
                  disabled={handle.isPending}
                >
                  {t('shifts.transferReject')}
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={() => run('cancel')}
                disabled={handle.isPending}
              >
                {t('shifts.transferCancel')}
              </Button>
            </div>
          )}

          {assigning && (
            <div className="flex flex-col gap-1.5">
              <select
                className="bg-bg-base border border-border-default rounded-sm px-2 py-1.5 text-xs text-text-primary"
                value={picked}
                onChange={e => setPicked(e.target.value)}
              >
                <option value="">{t('shifts.reassignSelectPlaceholder')}</option>
                {eligible.map(e => (
                  <option key={e.id} value={e.id}>
                    {[e.first_name, e.last_name].filter(Boolean).join(' ') || `#${e.id}`}
                    {e.specialization?.length ? ` (${e.specialization.join(', ')})` : ''}
                  </option>
                ))}
              </select>
              <div className="flex gap-1.5 justify-end">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setAssigning(false)
                    setPicked('')
                  }}
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  size="sm"
                  onClick={() => run('approve', Number(picked))}
                  disabled={!picked || handle.isPending}
                >
                  {t('shifts.transferConfirmAssign')}
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
