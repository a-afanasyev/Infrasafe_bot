import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import {
  useCompleteOccurrence,
  useCreateOccurrence,
  useGenerateOccurrences,
  useRescheduleOccurrence,
} from '../../hooks/useElevatorCalendar'
import { emptyToNull } from '../../utils/elevatorsFormat'
import { OCCURRENCE_KINDS, type ElevatorOccurrence, type OccurrenceKind } from '../../types/elevators'

/**
 * Диалоги графика ТО/освидетельствований: создать / сгенерировать / перенести /
 * выполнено. Один файл — четыре маленьких диалога с общим каркасом.
 */

interface ShellProps {
  open: boolean
  title: string
  onClose: () => void
  onSubmit: () => void
  canSubmit: boolean
  pending: boolean
  submitLabel: string
  children: React.ReactNode
}

function DialogShell({ open, title, onClose, onSubmit, canSubmit, pending, submitLabel, children }: ShellProps) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">{children}</div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={pending}>{t('common.cancel')}</Button>
          <Button onClick={onSubmit} disabled={!canSubmit || pending}>
            {pending ? t('common.saving') : submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  )
}

function KindSelect({ id, value, onChange }: { id: string; value: OccurrenceKind; onChange: (k: OccurrenceKind) => void }) {
  const { t } = useTranslation()
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value as OccurrenceKind)}>
      {OCCURRENCE_KINDS.map((k) => (
        <option key={k} value={k}>{t(`elevators.occurrences.kind.${k}`)}</option>
      ))}
    </Select>
  )
}

/** Render-time reset формы при открытии (паттерн MaterialFormDialog). */
function useOpenReset(open: boolean, reset: () => void) {
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) reset()
  }
}

// ── Создать пункт ────────────────────────────────────────────────────

export function CreateOccurrenceDialog({ elevatorId, open, onClose }: { elevatorId: number; open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const mutation = useCreateOccurrence(elevatorId)
  const [kind, setKind] = useState<OccurrenceKind>('maintenance')
  const [dueOn, setDueOn] = useState('')
  useOpenReset(open, () => { setKind('maintenance'); setDueOn('') })

  return (
    <DialogShell
      open={open} title={t('elevators.occurrences.createTitle')} onClose={onClose}
      canSubmit={dueOn !== ''} pending={mutation.isPending} submitLabel={t('common.create')}
      onSubmit={() => mutation.mutate({ kind, due_on: dueOn }, { onSuccess: onClose })}
    >
      <Field id="occ-create-kind" label={t('elevators.occurrences.kindLabel')}>
        <KindSelect id="occ-create-kind" value={kind} onChange={setKind} />
      </Field>
      <Field id="occ-create-due" label={t('elevators.occurrences.dueOn')}>
        <Input id="occ-create-due" type="date" value={dueOn} onChange={(e) => setDueOn(e.target.value)} />
      </Field>
    </DialogShell>
  )
}

// ── Сгенерировать ────────────────────────────────────────────────────

export function GenerateOccurrencesDialog({ elevatorId, open, onClose }: { elevatorId: number; open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const mutation = useGenerateOccurrences(elevatorId)
  const [kind, setKind] = useState<OccurrenceKind>('maintenance')
  const [start, setStart] = useState('')
  const [everyMonths, setEveryMonths] = useState('1')
  const [count, setCount] = useState('12')
  useOpenReset(open, () => { setKind('maintenance'); setStart(''); setEveryMonths('1'); setCount('12') })

  const every = Number(everyMonths)
  const cnt = Number(count)
  const canSubmit = start !== '' && Number.isInteger(every) && every > 0 && Number.isInteger(cnt) && cnt > 0

  return (
    <DialogShell
      open={open} title={t('elevators.occurrences.generateTitle')} onClose={onClose}
      canSubmit={canSubmit} pending={mutation.isPending} submitLabel={t('elevators.actions.generate')}
      onSubmit={() => mutation.mutate({ kind, start, every_months: every, count: cnt }, { onSuccess: onClose })}
    >
      <Field id="occ-gen-kind" label={t('elevators.occurrences.kindLabel')}>
        <KindSelect id="occ-gen-kind" value={kind} onChange={setKind} />
      </Field>
      <Field id="occ-gen-start" label={t('elevators.occurrences.start')}>
        <Input id="occ-gen-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
      </Field>
      <Field id="occ-gen-every" label={t('elevators.occurrences.everyMonths')}>
        <Input id="occ-gen-every" type="number" min="1" value={everyMonths} onChange={(e) => setEveryMonths(e.target.value)} />
      </Field>
      <Field id="occ-gen-count" label={t('elevators.occurrences.count')}>
        <Input id="occ-gen-count" type="number" min="1" value={count} onChange={(e) => setCount(e.target.value)} />
      </Field>
    </DialogShell>
  )
}

// ── Перенести ────────────────────────────────────────────────────────

export function RescheduleOccurrenceDialog({ elevatorId, occurrence, onClose }: { elevatorId: number; occurrence: ElevatorOccurrence | null; onClose: () => void }) {
  const { t } = useTranslation()
  const mutation = useRescheduleOccurrence(elevatorId)
  const [dueOn, setDueOn] = useState('')
  useOpenReset(occurrence !== null, () => setDueOn(occurrence?.due_on ?? ''))

  return (
    <DialogShell
      open={occurrence !== null} title={t('elevators.occurrences.rescheduleTitle')} onClose={onClose}
      canSubmit={dueOn !== '' && dueOn !== occurrence?.due_on} pending={mutation.isPending}
      submitLabel={t('elevators.actions.reschedule')}
      onSubmit={() => occurrence && mutation.mutate({ id: occurrence.id, due_on: dueOn }, { onSuccess: onClose })}
    >
      <Field id="occ-resched-due" label={t('elevators.occurrences.dueOn')}>
        <Input id="occ-resched-due" type="date" value={dueOn} onChange={(e) => setDueOn(e.target.value)} />
      </Field>
    </DialogShell>
  )
}

// ── Выполнено ────────────────────────────────────────────────────────

export function CompleteOccurrenceDialog({ elevatorId, occurrence, onClose }: { elevatorId: number; occurrence: ElevatorOccurrence | null; onClose: () => void }) {
  const { t } = useTranslation()
  const mutation = useCompleteOccurrence(elevatorId)
  const [comment, setComment] = useState('')
  const [requestNumber, setRequestNumber] = useState('')
  const [certNumber, setCertNumber] = useState('')
  const [certValidUntil, setCertValidUntil] = useState('')
  const [certActUrl, setCertActUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  useOpenReset(occurrence !== null, () => {
    setComment(''); setRequestNumber(''); setCertNumber(''); setCertValidUntil(''); setCertActUrl(''); setError(null)
  })

  const isCert = occurrence?.kind === 'certification'
  const certFilled = certNumber.trim() !== '' && certValidUntil !== '' && certActUrl.trim() !== ''

  const submit = () => {
    if (!occurrence) return
    if (isCert && !certFilled) {
      setError(t('elevators.occurrences.certRequired'))
      return
    }
    setError(null)
    mutation.mutate(
      {
        id: occurrence.id,
        comment: emptyToNull(comment),
        request_number: emptyToNull(requestNumber),
        ...(isCert
          ? { cert_number: certNumber.trim(), cert_valid_until: certValidUntil, cert_act_url: certActUrl.trim() }
          : {}),
      },
      { onSuccess: onClose },
    )
  }

  return (
    <DialogShell
      open={occurrence !== null} title={t('elevators.occurrences.completeTitle')} onClose={onClose}
      canSubmit pending={mutation.isPending} submitLabel={t('elevators.actions.complete')} onSubmit={submit}
    >
      <Field id="occ-done-comment" label={t('elevators.occurrences.comment')}>
        <Textarea id="occ-done-comment" value={comment} onChange={(e) => setComment(e.target.value)} />
      </Field>
      <Field id="occ-done-request" label={t('elevators.occurrences.requestNumber')}>
        <Input id="occ-done-request" value={requestNumber} onChange={(e) => setRequestNumber(e.target.value)} />
      </Field>
      {isCert && (
        <>
          <p className="text-[12px] text-text-muted">{t('elevators.occurrences.certFieldsHint')}</p>
          <Field id="occ-done-cert-number" label={t('elevators.form.certNumber')}>
            <Input id="occ-done-cert-number" value={certNumber} onChange={(e) => setCertNumber(e.target.value)} />
          </Field>
          <Field id="occ-done-cert-until" label={t('elevators.form.certValidUntil')}>
            <Input id="occ-done-cert-until" type="date" value={certValidUntil} onChange={(e) => setCertValidUntil(e.target.value)} />
          </Field>
          <Field id="occ-done-cert-url" label={t('elevators.form.certActUrl')}>
            <Input id="occ-done-cert-url" type="url" value={certActUrl} onChange={(e) => setCertActUrl(e.target.value)} />
          </Field>
        </>
      )}
      {error && <p role="alert" className="text-[13px] text-red">{error}</p>}
    </DialogShell>
  )
}
