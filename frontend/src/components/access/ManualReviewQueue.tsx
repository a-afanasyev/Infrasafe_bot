import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAccessEvents, useResolveEvent } from '../../hooks/useAccessRegistry'
import type { AccessEventRow } from '../../types/access'
import { formatDateTime } from '../../utils/accessFormat'
import ResolveDialog, { type ResolveTarget, type ResolveSubmit } from './ResolveDialog'
import AccessPhotos from './AccessPhotos'
import LoadingSpinner from '../shared/LoadingSpinner'
import EmptyState from '../shared/EmptyState'
import { Button } from '@/components/ui/button'
import { safeErrorMessage } from '@/utils/errorMessage'

/**
 * Очередь ручной проверки (manual_review) для охранника: события, ожидающие
 * решения оператора. По каждому — время ожидания, номер/место и действия
 * «Открыть с причиной» (resolve manual_open) / «Отказать» (resolve deny).
 */

// Время ожидания с момента фиксации (грубый таймер: бэк не отдаёт дедлайн в
// строке списка — он живёт в деталях решения review_deadline_at).
function waitMinutes(capturedAt: string): number {
  const ms = Date.now() - new Date(capturedAt).getTime()
  return Math.max(0, Math.floor(ms / 60_000))
}

interface QueuedTarget {
  event: AccessEventRow
  action: 'manual_open' | 'deny'
}

export default function ManualReviewQueue({
  onOpenDetail,
}: {
  onOpenDetail?: (event: AccessEventRow) => void
}) {
  const { t } = useTranslation()
  // Очередь = текущие manual_review-события (decision-фильтр; status не фильтруем
  // на бэке — pending-исход у этих событий по построению движка).
  const { data, isLoading, isError } = useAccessEvents({ decision: 'manual_review', limit: 50 })
  const resolve = useResolveEvent()
  const [target, setTarget] = useState<QueuedTarget | null>(null)

  const events = data?.items ?? []

  const dialogTarget: ResolveTarget | null = target
    ? { action: target.action, defaultBarrierId: target.event.gate_id }
    : null

  function handleSubmit({ reason, barrierId }: ResolveSubmit) {
    if (!target) return
    const { event, action } = target
    resolve.mutate(
      {
        eventId: event.event_id,
        payload:
          action === 'manual_open'
            ? {
                action: 'manual_open',
                reason,
                barrier_id: barrierId,
                decision_id: event.decision_id ?? undefined,
              }
            : { action: 'deny', reason },
      },
      {
        onSuccess: () => {
          toast.success(
            action === 'manual_open'
              ? t('accessControl.resolve.openedToast')
              : t('accessControl.resolve.deniedToast'),
          )
          setTarget(null)
        },
        onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
      },
    )
  }

  if (isLoading) return <LoadingSpinner />
  if (isError)
    return <p className="text-[13px] text-red px-1">{t('common.error')}</p>

  if (events.length === 0) {
    return (
      <div className="rounded-default border border-dashed border-border-default bg-bg-card">
        <EmptyState icon="✅" title={t('accessControl.queue.empty')} subtitle={t('accessControl.queue.emptyDesc')} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {events.map((event) => {
        const mins = waitMinutes(event.captured_at)
        const location =
          [
            event.zone_id != null ? `${t('accessControl.zone')} ${event.zone_id}` : null,
            event.gate_id != null ? `${t('accessControl.gate')} ${event.gate_id}` : null,
          ]
            .filter(Boolean)
            .join(' · ') || '—'
        return (
          <div
            key={event.id}
            className="flex flex-wrap items-center gap-4 rounded-default border border-amber-300/60 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-900/10 px-4 py-3"
          >
            <div
              className={onOpenDetail ? 'flex-1 min-w-[220px] cursor-pointer' : 'flex-1 min-w-[220px]'}
              onClick={() => onOpenDetail?.(event)}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[15px] font-semibold text-text-primary">
                  {event.plate_number_normalized ?? '—'}
                </span>
                <span className="rounded-full bg-amber-200/70 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 px-2 py-0.5 text-[11px] font-medium">
                  {t('accessControl.queue.waiting', { min: mins })}
                </span>
                {/* Компактный индикатор ответа жителя (совещательно), если строка
                    очереди его содержит. Берём последний ответ. Нет данных — скрыто. */}
                {event.resident_confirmations && event.resident_confirmations.length > 0 && (
                  (() => {
                    const last = event.resident_confirmations[event.resident_confirmations.length - 1]
                    const isConfirm = last.response === 'confirm'
                    return (
                      <span
                        className={
                          'rounded-full px-2 py-0.5 text-[11px] font-medium ' +
                          (isConfirm
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                            : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300')
                        }
                      >
                        {isConfirm
                          ? t('accessControl.residentResponse.queueConfirmed')
                          : t('accessControl.residentResponse.queueDenied')}
                      </span>
                    )
                  })()
                )}
              </div>
              <div className="mt-0.5 text-[12px] text-text-muted">
                {location} · {formatDateTime(event.occurred_at ?? event.captured_at)}
              </div>
            </div>
            {/* Миниатюры авто+номера, чтобы оператор видел ТС при решении (§11). */}
            <AccessPhotos
              size="compact"
              overviewUrl={event.overview_photo_url}
              plateUrl={event.plate_photo_url}
              className="w-[200px]"
            />
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => setTarget({ event, action: 'manual_open' })}
              >
                {t('accessControl.queue.openAction')}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => setTarget({ event, action: 'deny' })}
              >
                {t('accessControl.queue.denyAction')}
              </Button>
            </div>
          </div>
        )
      })}

      <ResolveDialog
        target={dialogTarget}
        loading={resolve.isPending}
        onClose={() => setTarget(null)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
