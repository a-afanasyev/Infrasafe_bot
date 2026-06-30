import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAccessPassDetail, useUpdatePass } from '../../hooks/useAccessRegistry'
import { AccessStatusBadge } from './AccessBadges'
import LoadingSpinner from '../shared/LoadingSpinner'
import { MetaField, ApplicantAddressZones } from './AccessMeta'
import type { UpdatePassPayload, ZoneRef } from '../../types/access'

/**
 * Деталь пропуска + правка (менеджер): заявитель/адрес/зона, продление срока,
 * лимит въездов, номер ТС и отзыв пропуска. Read-only для не-менеджера.
 */
interface Props {
  passId: number | null
  canManage: boolean
  onClose: () => void
}

/** ISO → значение для <input type="datetime-local"> (локальное время, без TZ). */
function toLocalInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function PassDetailDialog({ passId, canManage, onClose }: Props) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAccessPassDetail(passId)
  const updatePass = useUpdatePass()
  const pass = data?.pass

  const [validUntil, setValidUntil] = useState('')
  const [maxEntries, setMaxEntries] = useState('')
  const [plate, setPlate] = useState('')

  // Префилл формы при загрузке пропуска (render-time sync по id).
  const [syncId, setSyncId] = useState<number | null>(null)
  if (pass && pass.id !== syncId) {
    setSyncId(pass.id)
    setValidUntil(toLocalInput(pass.valid_until))
    setMaxEntries(String(pass.max_entries))
    setPlate(pass.plate_number_original ?? pass.plate_number_normalized ?? '')
  }

  const editable = canManage && pass?.status === 'active'

  function handleSave() {
    if (!pass) return
    const payload: UpdatePassPayload = {}
    if (validUntil) payload.valid_until = new Date(validUntil).toISOString()
    const me = Number(maxEntries)
    if (Number.isFinite(me) && me >= 1) payload.max_entries = me
    payload.plate_number_original = plate.trim() || null
    updatePass.mutate({ passId: pass.id, payload }, { onSuccess: onClose })
  }

  function handleRevoke() {
    if (!pass) return
    updatePass.mutate(
      { passId: pass.id, payload: { status: 'revoked' } },
      { onSuccess: onClose },
    )
  }

  const zoneList: ZoneRef[] = data?.zone ? [data.zone] : []

  return (
    <Dialog open={passId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('accessControl.passDetail.title')}</DialogTitle>
          <DialogDescription>
            {pass
              ? t(`accessControl.passes.passType.${pass.pass_type}`, {
                  defaultValue: pass.pass_type,
                })
              : ' '}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <LoadingSpinner />}
        {isError && <p className="text-[13px] text-red">{t('common.error')}</p>}

        {data && pass && (
          <div className="flex flex-col gap-5">
            <div className="grid grid-cols-2 gap-3">
              <MetaField
                label={t('accessControl.columns.status')}
                value={<AccessStatusBadge status={pass.status} />}
              />
              <MetaField
                label={t('accessControl.passes.entries')}
                value={`${pass.used_entries}/${pass.max_entries}`}
              />
            </div>

            <ApplicantAddressZones
              applicant={data.applicant}
              address={data.address}
              zones={zoneList}
            />

            {editable ? (
              <div className="flex flex-col gap-3 border-t border-border-default pt-4">
                <h3 className="text-[12px] font-semibold uppercase tracking-wider text-text-secondary">
                  {t('accessControl.passDetail.editTitle')}
                </h3>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="pd-until">{t('accessControl.passes.validUntil')}</Label>
                  <Input
                    id="pd-until"
                    type="datetime-local"
                    value={validUntil}
                    onChange={(e) => setValidUntil(e.target.value)}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="pd-max">{t('accessControl.passDetail.maxEntries')}</Label>
                    <Input
                      id="pd-max"
                      type="number"
                      min={1}
                      value={maxEntries}
                      onChange={(e) => setMaxEntries(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="pd-plate">{t('accessControl.columns.plate')}</Label>
                    <Input
                      id="pd-plate"
                      value={plate}
                      onChange={(e) => setPlate(e.target.value)}
                      className="font-mono"
                    />
                  </div>
                </div>
              </div>
            ) : (
              <MetaField
                label={t('accessControl.passes.validUntil')}
                value={pass.valid_until ? new Date(pass.valid_until).toLocaleString() : '—'}
              />
            )}
          </div>
        )}

        {editable && (
          <DialogFooter className="justify-between">
            <Button
              variant="destructive"
              onClick={handleRevoke}
              disabled={updatePass.isPending}
            >
              {t('accessControl.actions.revokePass')}
            </Button>
            <div className="flex gap-2">
              <Button variant="outline" onClick={onClose} disabled={updatePass.isPending}>
                {t('common.cancel')}
              </Button>
              <Button onClick={handleSave} disabled={updatePass.isPending}>
                {updatePass.isPending ? t('common.saving') : t('common.save')}
              </Button>
            </div>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
