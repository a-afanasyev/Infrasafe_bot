import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ResidentProfile } from '../../types/api'
import {
  useApproveResident,
  useBlockResident,
  useUnblockResident,
} from '../../hooks/useResidents'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import ConfirmDialog from '../shared/ConfirmDialog'

interface Props {
  resident: ResidentProfile
}

/** Роли, при которых операции с аккаунтом отсюда запрещены бэкендом (Т2).
 *  `resource_meter_entry` — капабилити жителя, а не рабочая роль. */
const RESIDENT_ONLY_ROLES = new Set(['applicant', 'resource_meter_entry'])

export default function ResidentAccountActions({ resident }: Props) {
  const { t } = useTranslation()
  const [blockOpen, setBlockOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [unblockOpen, setUnblockOpen] = useState(false)

  const approve = useApproveResident(resident.id)
  const block = useBlockResident(resident.id)
  const unblock = useUnblockResident(resident.id)

  const staffRoles = resident.roles.filter(r => !RESIDENT_ONLY_ROLES.has(r))
  // Все операции над аккаунтом мультиролевого прячем совсем, а не показываем
  // кнопку, которая гарантированно даст 409.
  //
  // Блокировка — потому что users.status общий на ВСЕ роли и отнял бы рабочий
  // доступ. Одобрение — потому что «Сотрудники» активируют через
  // activate_employee, который кроме status поднимает active_role до
  // стафф-роли; здешний путь сделал бы только половину, и приглашённый через
  // бота сотрудник остался бы без меню в боте.
  const isPureResident = staffRoles.length === 0
  const canApprove = isPureResident
  const canBlock = isPureResident
  const isBlocked = resident.status === 'blocked'
  const busy = approve.isPending || block.isPending || unblock.isPending

  return (
    <div className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-3">
      <div className="text-xs font-bold text-text-muted uppercase tracking-wider">
        {t('residents.sectionActions')}
      </div>

      <div className="flex gap-2 flex-wrap">
        {canApprove && resident.status === 'pending' && (
          <Button size="sm" disabled={busy} onClick={() => approve.mutate({})}>
            {t('residents.approveAccount')}
          </Button>
        )}

        {/* Триггер и форма взаимоисключающи: иначе повторный клик по кнопке
            затёр бы уже введённую причину. */}
        {canBlock && !isBlocked && !blockOpen && (
          <Button variant="destructive" size="sm" disabled={busy}
                  onClick={() => { setReason(''); setBlockOpen(true) }}>
            {t('residents.blockAccount')}
          </Button>
        )}

        {canBlock && isBlocked && (
          <Button variant="outline" size="sm" disabled={busy}
                  onClick={() => setUnblockOpen(true)}>
            {t('residents.unblockAccount')}
          </Button>
        )}
      </div>

      {!isPureResident && (
        <p className="text-[11px] text-text-muted m-0">
          {t('residents.blockHiddenForStaff', { roles: staffRoles.join(', ') })}
        </p>
      )}

      {blockOpen && (
        <div className="flex flex-col gap-2">
          <Textarea
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder={t('residents.blockReason')}
            aria-label={t('residents.blockReason')}
            autoFocus
          />
          <div className="flex items-center gap-2.5">
            <Button
              variant="destructive"
              size="sm"
              disabled={reason.trim().length < 3 || busy}
              onClick={() => block.mutate(
                { reason: reason.trim() },
                { onSuccess: () => setBlockOpen(false) },
              )}
            >
              {t('residents.blockSubmit')}
            </Button>
            <button
              onClick={() => setBlockOpen(false)}
              className="bg-transparent border-none cursor-pointer text-[13px] text-text-muted underline p-0"
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={unblockOpen}
        onOpenChange={setUnblockOpen}
        title={t('residents.unblockConfirm')}
        description={t('residents.unblockConfirmDesc')}
        confirmLabel={t('residents.unblockAccount')}
        variant="warning"
        loading={unblock.isPending}
        onConfirm={() => unblock.mutate()}
      />
    </div>
  )
}
