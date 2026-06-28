import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { useAccessEventDetail } from '../../hooks/useAccessRegistry'
import { DecisionBadge, ResidentResponseBadge } from './AccessBadges'
import AccessPhotos from './AccessPhotos'
import { formatDateTime } from '../../utils/accessFormat'
import LoadingSpinner from '../shared/LoadingSpinner'

/**
 * Деталь события доступа: камера-событие + цепочки решений, команд шлагбаума и
 * ручных открытий (§13.2). Открывается по клику на строку истории/очереди.
 */
interface Props {
  eventId: number | null
  onClose: () => void
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-bold uppercase tracking-wider text-text-muted">{label}</span>
      <span className="text-[13px] text-text-primary break-words">{value ?? '—'}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[12px] font-semibold uppercase tracking-wider text-text-secondary">
        {title}
      </h3>
      {children}
    </div>
  )
}

export default function AccessEventDetailDialog({ eventId, onClose }: Props) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAccessEventDetail(eventId)

  return (
    <Dialog open={eventId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('accessControl.detail.title')}</DialogTitle>
          <DialogDescription>
            {data ? `${t('accessControl.detail.eventId')}: ${data.camera_event.event_id}` : ' '}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <LoadingSpinner />}
        {isError && <p className="text-[13px] text-red">{t('common.error')}</p>}

        {data && (
          <div className="flex flex-col gap-5">
            {/* Камера-событие */}
            <Section title={t('accessControl.detail.cameraEvent')}>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t('accessControl.columns.time')} value={formatDateTime(data.camera_event.captured_at)} />
                <Field
                  label={t('accessControl.columns.direction')}
                  value={t(`accessControl.direction.${data.camera_event.direction}`, {
                    defaultValue: data.camera_event.direction,
                  })}
                />
                <Field
                  label={t('accessControl.columns.plate')}
                  value={
                    <span className="font-mono">
                      {data.camera_event.plate_number_original ??
                        data.camera_event.plate_number_normalized ??
                        '—'}
                    </span>
                  }
                />
                <Field label={t('accessControl.columns.source')} value={data.camera_event.source} />
                <Field label={t('accessControl.zone')} value={data.camera_event.zone_id ?? '—'} />
                <Field label={t('accessControl.gate')} value={data.camera_event.gate_id ?? '—'} />
                <Field label={t('accessControl.detail.vehicleClass')} value={data.camera_event.vehicle_class ?? '—'} />
                <Field label={t('accessControl.detail.color')} value={data.camera_event.color ?? '—'} />
              </div>
            </Section>

            {/* Фото проезда (§11): обзор авто + номер крупно */}
            <Section title={t('accessControl.photos.title')}>
              <AccessPhotos
                size="full"
                overviewUrl={data.camera_event.overview_photo_url}
                plateUrl={data.camera_event.plate_photo_url}
              />
            </Section>

            {/* Решения */}
            <Section title={t('accessControl.detail.decisions')}>
              {data.decisions.length === 0 ? (
                <p className="text-[13px] text-text-muted">—</p>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {data.decisions.map((d) => (
                    <div
                      key={d.id}
                      className="flex items-center gap-2 rounded-sm border border-border-default bg-bg-surface px-3 py-2"
                    >
                      <DecisionBadge decision={d.decision} />
                      <span className="text-[12px] text-text-muted">
                        {d.reason
                          ? t(`accessControl.reason.${d.reason}`, { defaultValue: d.reason })
                          : '—'}
                      </span>
                      <span className="ml-auto text-[12px] text-text-muted">
                        {formatDateTime(d.created_at)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            {/* Ответ жителя на спорный въезд (§14): совещательный сигнал —
                оператор всё равно решает open/deny. Пустой массив — не показываем. */}
            {data.resident_confirmations.length > 0 && (
              <Section title={t('accessControl.residentResponse.title')}>
                <p className="text-[12px] text-text-muted">
                  {t('accessControl.residentResponse.advisory')}
                </p>
                <div className="flex flex-col gap-1.5">
                  {data.resident_confirmations.map((rc, i) => (
                    <div
                      key={`${rc.user_id}-${rc.created_at}-${i}`}
                      className="flex items-center gap-2 rounded-sm border border-border-default bg-bg-surface px-3 py-2 text-[12px]"
                    >
                      <span className="text-text-primary">
                        {t('accessControl.residentResponse.resident', { id: rc.user_id })}
                      </span>
                      <ResidentResponseBadge response={rc.response} />
                      <span className="ml-auto text-text-muted">{formatDateTime(rc.created_at)}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Команды шлагбаума */}
            <Section title={t('accessControl.detail.commands')}>
              {data.barrier_commands.length === 0 ? (
                <p className="text-[13px] text-text-muted">—</p>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {data.barrier_commands.map((c) => (
                    <div
                      key={c.command_id}
                      className="flex items-center gap-2 rounded-sm border border-border-default bg-bg-surface px-3 py-2 text-[12px]"
                    >
                      <span className="font-medium text-text-primary">{c.command_type}</span>
                      <span className="text-text-muted">{c.status}</span>
                      <span className="ml-auto text-text-muted">{formatDateTime(c.created_at)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            {/* Ручные открытия */}
            <Section title={t('accessControl.detail.manualOpenings')}>
              {data.manual_openings.length === 0 ? (
                <p className="text-[13px] text-text-muted">—</p>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {data.manual_openings.map((m) => (
                    <div
                      key={m.id}
                      className="flex items-center gap-2 rounded-sm border border-border-default bg-bg-surface px-3 py-2 text-[12px]"
                    >
                      <span className="text-text-primary">{m.reason}</span>
                      <span className="ml-auto text-text-muted">{formatDateTime(m.created_at)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
