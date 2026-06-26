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
import type { CreateTaxiPassPayload } from '../../types/access'

/**
 * Диалог-форма создания taxi-пропуска (POST /passes/taxi). Обязательны квартира,
 * зона и срок действия «до». Даты — datetime-local; в payload уходят как ISO.
 */
interface Props {
  open: boolean
  loading?: boolean
  onClose: () => void
  onSubmit: (payload: CreateTaxiPassPayload) => void
}

interface FormState {
  apartmentId: string
  zoneId: string
  validFrom: string
  validUntil: string
  plate: string
  maxEntries: string
}

const EMPTY: FormState = {
  apartmentId: '',
  zoneId: '',
  validFrom: '',
  validUntil: '',
  plate: '',
  maxEntries: '1',
}

// datetime-local → ISO-строка (бэкенд принимает ISO 8601).
function toIso(local: string): string | undefined {
  if (!local.trim()) return undefined
  const d = new Date(local)
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString()
}

export default function TaxiPassFormDialog({ open, loading, onClose, onSubmit }: Props) {
  const { t } = useTranslation()
  const [form, setForm] = useState<FormState>(EMPTY)

  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) setForm(EMPTY)
  }

  const set = (patch: Partial<FormState>) => setForm((p) => ({ ...p, ...patch }))

  const apartmentId = Number(form.apartmentId)
  const zoneId = Number(form.zoneId)
  const validUntilIso = toIso(form.validUntil)
  const canSubmit =
    form.apartmentId.trim().length > 0 &&
    Number.isFinite(apartmentId) &&
    form.zoneId.trim().length > 0 &&
    Number.isFinite(zoneId) &&
    !!validUntilIso &&
    !loading

  function handleSubmit() {
    if (!canSubmit || !validUntilIso) return
    const maxEntriesNum = Number(form.maxEntries)
    const payload: CreateTaxiPassPayload = {
      apartment_id: apartmentId,
      zone_id: zoneId,
      valid_until: validUntilIso,
      valid_from: toIso(form.validFrom),
      plate_number_original: form.plate.trim() ? form.plate.trim() : undefined,
      max_entries:
        form.maxEntries.trim() && Number.isFinite(maxEntriesNum) ? maxEntriesNum : undefined,
    }
    onSubmit(payload)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('accessControl.taxiPassForm.title')}</DialogTitle>
          <DialogDescription>{t('accessControl.taxiPassForm.desc')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tp-apartment">{t('accessControl.taxiPassForm.apartmentId')}</Label>
              <Input
                id="tp-apartment"
                type="number"
                value={form.apartmentId}
                onChange={(e) => set({ apartmentId: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tp-zone">{t('accessControl.taxiPassForm.zoneId')}</Label>
              <Input
                id="tp-zone"
                type="number"
                value={form.zoneId}
                onChange={(e) => set({ zoneId: e.target.value })}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tp-plate">{t('accessControl.taxiPassForm.plate')}</Label>
            <Input
              id="tp-plate"
              value={form.plate}
              onChange={(e) => set({ plate: e.target.value })}
              placeholder={t('accessControl.taxiPassForm.platePlaceholder')}
              className="font-mono"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tp-from">{t('accessControl.taxiPassForm.validFrom')}</Label>
              <Input
                id="tp-from"
                type="datetime-local"
                value={form.validFrom}
                onChange={(e) => set({ validFrom: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tp-until">{t('accessControl.taxiPassForm.validUntil')}</Label>
              <Input
                id="tp-until"
                type="datetime-local"
                value={form.validUntil}
                onChange={(e) => set({ validUntil: e.target.value })}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="tp-entries">{t('accessControl.taxiPassForm.maxEntries')}</Label>
            <Input
              id="tp-entries"
              type="number"
              min={1}
              value={form.maxEntries}
              onChange={(e) => set({ maxEntries: e.target.value })}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!canSubmit} onClick={handleSubmit}>
            {loading ? t('common.creating') : t('accessControl.taxiPassForm.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
