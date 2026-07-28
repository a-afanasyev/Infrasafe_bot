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

/** Роли, при которых блокировка отсюда запрещена бэкендом (Т2).
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
  // Блокировка общая на ВСЕ роли (users.status), поэтому для мультиролевых её
  // прячем совсем, а не показываем кнопку, которая гарантированно даст 409.
  const canBlock = staffRoles.length === 0
  const isBlocked = resident.status === 'blocked'
  const busy = approve.isPending || block.isPending || unblock.isPending

  return (
    <div className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-3">
      <div className="text-xs font-bold text-text-muted uppercase tracking-wider">
        {t('residents.sectionActions')}
      </div>

      <div className="flex gap-2 flex-wrap">
        {resident.status === 'pending' && (
          <Button size="sm" disabled={busy} onClick={() => approve.mutate({})}>
            {t('residents.approveAccount')}
          </Button>
        )}

        {canBlock && !isBlocked && (
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

      {!canBlock && (
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
