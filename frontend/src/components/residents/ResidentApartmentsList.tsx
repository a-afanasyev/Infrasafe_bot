import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ResidentApartment } from '../../types/api'
import {
  useApproveBinding,
  useRejectBinding,
  useRemoveBinding,
  useUpdateBinding,
} from '../../hooks/useResidents'
import { formatDate as fmtDate } from '../../i18n/formatters'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import ConfirmDialog from '../shared/ConfirmDialog'
import { cn } from '@/lib/utils'

interface Props {
  residentId: number
  apartments: ResidentApartment[]
}

const STATUS_COLORS: Record<string, string> = {
  approved: 'var(--emerald)',
  pending: 'var(--amber)',
  rejected: 'var(--red)',
}

/** Адрес привязки: «двор · дом · кв. N». Двор и дом выводятся ИЗ квартиры —
 *  собственных полей у привязки нет, поэтому у жителя с двумя квартирами в
 *  разных дворах будет два разных двора, и это норма. */
function buildAddress(a: ResidentApartment, aptShort: string): string {
  const parts: string[] = []
  if (a.yard_name) parts.push(a.yard_name)
  if (a.building_address) parts.push(a.building_address)
  parts.push(`${aptShort} ${a.apartment_number}`)
  return parts.join(' · ')
}

export default function ResidentApartmentsList({ residentId, apartments }: Props) {
  const { t } = useTranslation()
  const [rejectingId, setRejectingId] = useState<number | null>(null)
  const [rejectComment, setRejectComment] = useState('')
  const [removeTarget, setRemoveTarget] = useState<ResidentApartment | null>(null)

  const approve = useApproveBinding(residentId)
  const reject = useRejectBinding(residentId)
  const update = useUpdateBinding(residentId)
  const remove = useRemoveBinding(residentId)

  const busy = approve.isPending || reject.isPending || update.isPending || remove.isPending

  if (apartments.length === 0) {
    return <div className="text-[13px] text-text-muted">{t('residents.noApartments')}</div>
  }

  return (
    <div className="flex flex-col gap-2">
      {apartments.map(a => {
        const color = STATUS_COLORS[a.status] ?? 'var(--text-muted)'
        const isApproved = a.status === 'approved'
        const isPending = a.status === 'pending'
        return (
          <div key={a.id} className="border border-border-default rounded-sm p-3 flex flex-col gap-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[13px] text-text-primary font-[family-name:var(--font-display)]">
                {buildAddress(a, t('residents.aptShort'))}
              </span>
              {a.is_primary && (
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-accent/15 text-accent">
                  {t('residents.primary')}
                </span>
              )}
              <span className={cn(
                'text-[11px] font-semibold px-2 py-0.5 rounded-full',
                a.is_owner ? 'bg-emerald/[.13] text-emerald' : 'bg-blue/[.13] text-blue',
              )}>
                {a.is_owner ? t('residents.owner') : t('residents.tenant')}
              </span>
              <span
                className="text-[11px] font-semibold px-2 py-0.5 rounded-full ml-auto"
                style={{ background: `color-mix(in srgb, ${color} 13%, transparent)`, color }}
              >
                {t(`residents.bindingStatus.${a.status}`, a.status)}
              </span>
            </div>

            <div className="text-[11px] text-text-muted font-[family-name:var(--font-display)]">
              {a.requested_at && t('residents.requestedAt', { date: fmtDate(a.requested_at, { dateStyle: 'short' }) })}
              {a.reviewed_at && ` · ${t('residents.reviewedAt', { date: fmtDate(a.reviewed_at, { dateStyle: 'short' }) })}`}
            </div>
            {a.admin_comment && (
              <div className="text-[12px] text-text-secondary italic">{a.admin_comment}</div>
            )}

            {/* Модерация заявки жителя — инлайн, как в очереди «Адресов» */}
            {rejectingId === a.id ? (
              <div className="flex flex-col gap-2">
                <Textarea
                  value={rejectComment}
                  onChange={e => setRejectComment(e.target.value)}
                  placeholder={t('residents.rejectReason')}
                  autoFocus
                />
                <div className="flex items-center gap-2.5">
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={rejectComment.trim().length < 3 || busy}
                    onClick={() => reject.mutate(
                      { uaId: a.id, comment: rejectComment.trim() },
                      { onSuccess: () => { setRejectingId(null); setRejectComment('') } },
                    )}
                  >
                    {t('residents.rejectSubmit')}
                  </Button>
                  <button
                    onClick={() => { setRejectingId(null); setRejectComment('') }}
                    className="bg-transparent border-none cursor-pointer text-[13px] text-text-muted underline p-0"
                  >
                    {t('common.cancel')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2 flex-wrap">
                {isPending && (
                  <>
                    <Button size="sm" disabled={busy}
                            onClick={() => approve.mutate({ uaId: a.id })}>
                      {t('residents.approveBinding')}
                    </Button>
                    <Button variant="destructive" size="sm" disabled={busy}
                            onClick={() => { setRejectingId(a.id); setRejectComment('') }}>
                      {t('residents.rejectBinding')}
                    </Button>
                  </>
                )}
                {isApproved && (
                  <>
                    <Button variant="outline" size="sm" disabled={busy}
                            onClick={() => update.mutate({ uaId: a.id, is_owner: !a.is_owner })}>
                      {a.is_owner ? t('residents.markTenant') : t('residents.markOwner')}
                    </Button>
                    {!a.is_primary && (
                      <Button variant="outline" size="sm" disabled={busy}
                              onClick={() => update.mutate({ uaId: a.id, is_primary: true })}>
                        {t('residents.makePrimaryAction')}
                      </Button>
                    )}
                  </>
                )}
                <Button variant="ghost" size="sm" disabled={busy}
                        className="text-red ml-auto"
                        onClick={() => setRemoveTarget(a)}>
                  {t('residents.detach')}
                </Button>
              </div>
            )}
          </div>
        )
      })}

      <ConfirmDialog
        open={removeTarget !== null}
        onOpenChange={open => { if (!open) setRemoveTarget(null) }}
        title={t('residents.detachConfirm')}
        description={removeTarget
          ? t('residents.detachConfirmDesc', {
              address: buildAddress(removeTarget, t('residents.aptShort')),
            })
          : ''}
        confirmLabel={t('residents.detach')}
        variant="danger"
        loading={remove.isPending}
        onConfirm={() => {
          if (removeTarget) remove.mutate(removeTarget.id)
          setRemoveTarget(null)
        }}
      />
    </div>
  )
}
