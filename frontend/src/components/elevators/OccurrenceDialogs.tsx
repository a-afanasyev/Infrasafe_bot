import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { DialogShell, Field } from './DialogShell'
import { useOpenReset } from '../../hooks/useOpenReset'
import {
  useCompleteOccurrence,
  useCreateOccurrence,
  useGenerateOccurrences,
  useRescheduleOccurrence,
} from '../../hooks/useElevatorCalendar'
import { emptyToNull, isHttpUrl } from '../../utils/elevatorsFormat'
import { ELEVATOR_FIELD_MAX } from '../../utils/elevatorForm'
import {
  MAX_REASON_LEN,
  OCCURRENCE_KINDS,
  type ElevatorOccurrence,
  type OccurrenceKind,
} from '../../types/elevators'

/**
 * Диалоги графика ТО/освидетельствований: создать / сгенерировать / перенести /
 * выполнено. Общий каркас — `DialogShell`.
 */

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
        <Input id="occ-gen-every" type="number" min={1} value={everyMonths} onChange={(e) => setEveryMonths(e.target.value)} />
      </Field>
      <Field id="occ-gen-count" label={t('elevators.occurrences.count')}>
        <Input id="occ-gen-count" type="number" min={1} value={count} onChange={(e) => setCount(e.target.value)} />
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
    if (isCert && !isHttpUrl(certActUrl.trim())) {
      setError(t('elevators.form.invalidUrl'))
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
        <Textarea id="occ-done-comment" value={comment} maxLength={MAX_REASON_LEN} onChange={(e) => setComment(e.target.value)} />
      </Field>
      <Field id="occ-done-request" label={t('elevators.occurrences.requestNumber')}>
        <Input id="occ-done-request" value={requestNumber} onChange={(e) => setRequestNumber(e.target.value)} />
      </Field>
      {isCert && (
        <>
          <p className="text-[12px] text-text-muted">{t('elevators.occurrences.certFieldsHint')}</p>
          <Field id="occ-done-cert-number" label={t('elevators.form.certNumber')}>
            <Input id="occ-done-cert-number" maxLength={ELEVATOR_FIELD_MAX.cert_number} value={certNumber} onChange={(e) => setCertNumber(e.target.value)} />
          </Field>
          <Field id="occ-done-cert-until" label={t('elevators.form.certValidUntil')}>
            <Input id="occ-done-cert-until" type="date" value={certValidUntil} onChange={(e) => setCertValidUntil(e.target.value)} />
          </Field>
          <Field id="occ-done-cert-url" label={t('elevators.form.certActUrl')}>
            <Input id="occ-done-cert-url" type="url" maxLength={ELEVATOR_FIELD_MAX.cert_act_url} value={certActUrl} onChange={(e) => setCertActUrl(e.target.value)} />
          </Field>
        </>
      )}
      {error && <p role="alert" className="text-[13px] text-red">{error}</p>}
    </DialogShell>
  )
}
