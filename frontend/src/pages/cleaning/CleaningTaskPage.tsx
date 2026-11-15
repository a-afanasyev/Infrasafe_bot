import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { usePageTitle } from '../../hooks/usePageTitle'
import { usePersonName } from '../../hooks/usePersonName'
import {
  useCleaningPhotoUrl,
  useCleaningStaff,
  useCleaningTaskCard,
  useDecideCleaningTask,
  useReassignCleaningTask,
} from '../../hooks/useCleaning'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import { shortDate } from '../../features/cleaning/dates'
import type { CleaningPhotoInfo, CleaningTaskCard } from '../../types/cleaning'

/**
 * Карточка задания уборки (/dashboard/cleaning/tasks/:id, manager): почему
 * задание на проверке, фото точек с уровнем доверия, поздние доказательства,
 * журнал и решение. Решение уходит с версией задания: если за это время пришла
 * жалоба или фото, сервер ответит «обновите» вместо слепой перезаписи.
 */
const CARD = 'bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-3'
const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—')

function slotName(slot: string, t: (key: string, options?: Record<string, unknown>) => string): string {
  return slot.startsWith('floor:') ? t('cleaning.task.floor', { n: slot.slice(6) }) : t(`cleaning.point.${slot.slice(6)}`, { defaultValue: slot.slice(6) })
}

function Photo({ photo }: { photo: CleaningPhotoInfo }) {
  const { t } = useTranslation()
  const [zoom, setZoom] = useState(false)
  const { data: url } = useCleaningPhotoUrl(photo.id, photo.has_file)
  const { data: full } = useCleaningPhotoUrl(photo.id, photo.has_file && zoom, true)
  const label = slotName(photo.slot, t)
  return (
    <figure className="flex flex-col gap-1 text-[12px] text-text-primary">
      {zoom && (
        <button
          type="button" autoFocus aria-label={t('common.close')} onClick={() => setZoom(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setZoom(false) }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
        >
          <img src={full ?? url} alt={label} className="max-h-full max-w-full rounded-default object-contain" />
        </button>
      )}
      {url
        ? (
          <button type="button" onClick={() => setZoom(true)} aria-label={t('cleaning.task.openPhoto', { label })}>
            <img src={url} alt={label} className="h-40 w-full rounded-default object-cover" />
          </button>
        )
        : <div className="flex h-40 items-center justify-center rounded-default border border-border-default text-text-muted">{t('cleaning.task.noFile')}</div>}
      <figcaption>
        <span className="font-semibold">{label}</span> · {time(photo.received_at)}
        {photo.trust_level && <> · {t(`cleaning.trust.${photo.trust_level}`)}</>}
        {photo.refusal_code && <> · {t(`twa.cleaning.refused.${photo.refusal_code}`, { defaultValue: photo.refusal_code })}</>}
      </figcaption>
    </figure>
  )
}

function Decision({ card }: { card: CleaningTaskCard }) {
  const { t } = useTranslation()
  const person = usePersonName()
  const decide = useDecideCleaningTask(card.task.id)
  const reassign = useReassignCleaningTask(card.task.id)
  const staff = useCleaningStaff()
  const [comment, setComment] = useState('')
  const { status } = card.task
  const send = (to: string) => decide.mutate({ to, version: card.version, ...(comment.trim() ? { comment: comment.trim() } : {}) })
  const closed = status === 'missed' || status === 'expired' || status === 'rejected'
  const needsComment = comment.trim() === ''

  return (
    <section className={CARD} aria-label={t('cleaning.task.decision')}>
      <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.task.decision')}</h2>
      {(status === 'review' || closed) && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cleaning-comment">{t('cleaning.task.comment')}</Label>
          <Textarea id="cleaning-comment" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {status === 'review' && (
          <>
            <Button type="button" disabled={decide.isPending} onClick={() => send('accepted')}>{t('cleaning.task.accept')}</Button>
            <Button type="button" variant="outline" className="text-red" disabled={decide.isPending || needsComment} onClick={() => send('rejected')}>{t('cleaning.task.reject')}</Button>
            <Button type="button" variant="ghost" disabled={decide.isPending} onClick={() => send('in_progress')}>{t('cleaning.task.returnForRetake')}</Button>
          </>
        )}
        {status === 'accepted' && (
          <Button type="button" variant="outline" disabled={decide.isPending} onClick={() => send('review')}>{t('cleaning.task.reopen')}</Button>
        )}
        {closed && (
          <Button type="button" disabled={decide.isPending || needsComment} onClick={() => send('accepted')}>{t('cleaning.task.acceptManually')}</Button>
        )}
      </div>
      {(status === 'planned' || status === 'in_progress') && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cleaning-reassign">{t('cleaning.task.reassign')}</Label>
          <select
            id="cleaning-reassign" value="" disabled={reassign.isPending}
            className="h-9 max-w-xs rounded-default border border-border-default bg-bg-card px-2 text-[13px] text-text-primary"
            onChange={(e) => reassign.mutate(Number(e.target.value))}
          >
            <option value="">{t('cleaning.task.chooseCleaner')}</option>
            {(staff.data?.cleaners ?? []).filter((c) => c.user_id !== card.task.responsible_id).map((c) => (
              <option key={c.user_id} value={c.user_id}>{person.full(c, `#${c.user_id}`)}</option>
            ))}
          </select>
        </div>
      )}
      <p className="text-[12px] text-text-muted">{t('cleaning.task.decisionNote')}</p>
    </section>
  )
}

export default function CleaningTaskPage() {
  const { t } = useTranslation()
  const { id } = useParams()
  const taskId = Number(id)
  usePageTitle(t('cleaning.task.title'))
  const card = useCleaningTaskCard(taskId)

  if (card.isLoading) return <LoadingSpinner />
  if (card.isError || !card.data) return <div className="p-6"><p className="text-[13px] text-red">{t('common.error')}</p></div>

  const { task, current, evidence, other, events, complaints } = card.data
  const verdict = [...events].reverse().find((event) => event.kind === 'completed')
  const reasons = verdict?.payload?.reasons ?? []
  const missing = card.data.slots_required.filter((slot) => !current.some((photo) => photo.slot === slot))

  return (
    <div className="flex flex-col gap-4 p-6">
      <div>
        <Link to="/dashboard/cleaning/control" className="text-[13px] font-medium text-accent">← {t('cleaning.control.title')}</Link>
        <h1 className="text-[18px] font-semibold text-text-primary">
          {task.address}, {t('cleaning.staff.entrance', { n: task.entrance })} — {shortDate(task.work_date)}
        </h1>
        <p className="text-[13px] text-text-muted">
          {t(`cleaning.status.${task.status}`)} · {card.data.works.map((w) => t(`cleaning.work.${w}`)).join(', ')} ·{' '}
          {t('cleaning.task.shot', { done: task.slots_done, total: task.slots_total })}
        </p>
      </div>

      {(reasons.length > 0 || verdict?.payload?.sampled) && (
        <section className={CARD} aria-label={t('cleaning.task.why')}>
          <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.task.why')}</h2>
          <ul className="list-disc pl-5 text-[13px] text-text-primary">
            {reasons.map((reason) => <li key={reason}>{t(`cleaning.reason.${reason}`, { defaultValue: reason })}</li>)}
            {verdict?.payload?.sampled && <li>{t('cleaning.reason.sampled')}</li>}
          </ul>
        </section>
      )}

      <section className={CARD} aria-label={t('cleaning.task.photos')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.task.photos')}</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {current.map((photo) => <Photo key={photo.id} photo={photo} />)}
        </div>
        {missing.length > 0 && (
          <p className="text-[13px] font-semibold text-red">
            {t('cleaning.task.missing', { list: missing.map((slot) => slotName(slot, t)).join(', ') })}
          </p>
        )}
      </section>

      {evidence.length > 0 && (
        <section className={CARD} aria-label={t('cleaning.task.evidence')}>
          <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.task.evidence')}</h2>
          <p className="text-[12px] text-text-muted">{t('cleaning.task.evidenceNote')}</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {evidence.map((photo) => <Photo key={photo.id} photo={photo} />)}
          </div>
        </section>
      )}

      {complaints.length > 0 && (
        <section className={CARD} aria-label={t('cleaning.control.complaints')}>
          <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.control.complaints')}</h2>
          <ul className="text-[13px] text-text-primary">
            {complaints.map((complaint) => (
              <li key={complaint.id} className="list-none">
                {time(complaint.created_at)} · {complaint.request_number ?? t('cleaning.control.noRequest')} · {t(`cleaning.complaint.${complaint.outcome}`)}
              </li>
            ))}
          </ul>
        </section>
      )}

      <Decision card={card.data} />

      <section className={CARD} aria-label={t('cleaning.task.journal')}>
        <h2 className="text-[14px] font-semibold text-text-primary">{t('cleaning.task.journal')}</h2>
        <ul className="flex flex-col gap-1 text-[13px] text-text-primary">
          {events.map((event, i) => (
            <li key={i} className="list-none">
              {time(event.created_at)} · {t(`cleaning.event.${event.kind}`, { defaultValue: event.kind })}
              {event.to_status && <> → {t(`cleaning.status.${event.to_status}`)}</>}
              {event.reason && <> — {event.reason}</>}
            </li>
          ))}
          {other.length > 0 && <li className="list-none text-text-muted">{t('cleaning.task.otherPhotos', { count: other.length })}</li>}
        </ul>
      </section>
    </div>
  )
}
