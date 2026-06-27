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
import { Select } from '@/components/ui/select'
import type {
  CreateAssignmentPayload,
  OwnershipType,
  SpotRow,
  UpdateAssignmentPayload,
} from '../../types/access'

/**
 * Диалог закрепления места за квартирой (POST /admin/spot-assignments).
 * Место выбирается из списка (spot_id), квартира — по ID. Для аренды (rented)
 * срок «до» (valid_until) обязателен — клиентская валидация запрещает отправку.
 */
const OWNERSHIP_TYPES: OwnershipType[] = ['owned', 'rented']

// datetime-local → ISO-строка (бэкенд принимает ISO 8601).
function toIso(local: string): string | undefined {
  if (!local.trim()) return undefined
  const d = new Date(local)
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString()
}

interface FormState {
  spotId: string
  apartmentId: string
  ownershipType: OwnershipType
  validFrom: string
  validUntil: string
}

const EMPTY: FormState = {
  spotId: '',
  apartmentId: '',
  ownershipType: 'owned',
  validFrom: '',
  validUntil: '',
}

interface Props {
  open: boolean
  spots: SpotRow[]
  /** Подпись места по id (zone code + spot code) — для опций селекта. */
  spotLabel: (spot: SpotRow) => string
  loading?: boolean
  onClose: () => void
  onSubmit: (payload: CreateAssignmentPayload) => void
}

export default function SpotAssignmentFormDialog({
  open,
  spots,
  spotLabel,
  loading,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const [form, setForm] = useState<FormState>(EMPTY)

  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) setForm(EMPTY)
  }

  const set = (patch: Partial<FormState>) => setForm((p) => ({ ...p, ...patch }))

  const spotId = Number(form.spotId)
  const apartmentId = Number(form.apartmentId)
  const isRented = form.ownershipType === 'rented'
  const validUntilIso = toIso(form.validUntil)
  // Для аренды срок «до» обязателен (клиентская валидация).
  const validUntilOk = !isRented || !!validUntilIso
  const canSubmit =
    form.spotId.trim().length > 0 &&
    Number.isFinite(spotId) &&
    form.apartmentId.trim().length > 0 &&
    Number.isFinite(apartmentId) &&
    validUntilOk &&
    !loading

  function handleSubmit() {
    if (!canSubmit) return
    const payload: CreateAssignmentPayload = {
      spot_id: spotId,
      apartment_id: apartmentId,
      ownership_type: form.ownershipType,
      valid_from: toIso(form.validFrom),
      valid_until: validUntilIso,
    }
    onSubmit(payload)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('accessControl.parking.assignmentForm.title')}</DialogTitle>
          <DialogDescription>{t('accessControl.parking.assignmentForm.desc')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sa-spot">{t('accessControl.parking.fields.spot')}</Label>
            <Select
              id="sa-spot"
              value={form.spotId}
              onChange={(e) => set({ spotId: e.target.value })}
            >
              <option value="">—</option>
              {spots.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {spotLabel(s)}
                </option>
              ))}
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sa-apartment">{t('accessControl.parking.fields.apartmentId')}</Label>
              <Input
                id="sa-apartment"
                type="number"
                value={form.apartmentId}
                onChange={(e) => set({ apartmentId: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sa-ownership">{t('accessControl.parking.fields.ownershipType')}</Label>
              <Select
                id="sa-ownership"
                value={form.ownershipType}
                onChange={(e) => set({ ownershipType: e.target.value as OwnershipType })}
              >
                {OWNERSHIP_TYPES.map((o) => (
                  <option key={o} value={o}>
                    {t(`accessControl.parking.ownershipType.${o}`)}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sa-from">{t('accessControl.parking.fields.validFrom')}</Label>
              <Input
                id="sa-from"
                type="datetime-local"
                value={form.validFrom}
                onChange={(e) => set({ validFrom: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sa-until">
                {t('accessControl.parking.fields.validUntil')}
                {isRented ? ' *' : ''}
              </Label>
              <Input
                id="sa-until"
                type="datetime-local"
                value={form.validUntil}
                onChange={(e) => set({ validUntil: e.target.value })}
              />
            </div>
          </div>

          {isRented && !validUntilOk && (
            <p className="text-[12px] text-red">
              {t('accessControl.parking.assignmentForm.validUntilRequired')}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!canSubmit} onClick={handleSubmit}>
            {loading ? t('common.creating') : t('accessControl.parking.assignmentForm.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Диалог продления закрепления (PATCH valid_until). Новый срок «до» обязателен.
 */
export function ExtendAssignmentDialog({
  open,
  loading,
  onClose,
  onSubmit,
}: {
  open: boolean
  loading?: boolean
  onClose: () => void
  onSubmit: (payload: UpdateAssignmentPayload) => void
}) {
  const { t } = useTranslation()
  const [validUntil, setValidUntil] = useState('')

  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) setValidUntil('')
  }

  const validUntilIso = toIso(validUntil)
  const canSubmit = !!validUntilIso && !loading

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t('accessControl.parking.extendForm.title')}</DialogTitle>
          <DialogDescription>{t('accessControl.parking.extendForm.desc')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ext-until">{t('accessControl.parking.fields.validUntil')}</Label>
          <Input
            id="ext-until"
            type="datetime-local"
            value={validUntil}
            onChange={(e) => setValidUntil(e.target.value)}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={!canSubmit}
            onClick={() => validUntilIso && onSubmit({ valid_until: validUntilIso })}
          >
            {loading ? t('common.saving') : t('accessControl.parking.extendForm.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
