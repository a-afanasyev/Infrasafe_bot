import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { useAccessVehicleDetail } from '../../hooks/useAccessRegistry'
import { AccessStatusBadge, DecisionBadge } from './AccessBadges'
import { formatDateTime } from '../../utils/accessFormat'
import LoadingSpinner from '../shared/LoadingSpinner'

/**
 * Деталь автомобиля: атрибуты + связи с квартирами + последние события проезда.
 */
interface Props {
  vehicleId: number | null
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

export default function VehicleDetailDialog({ vehicleId, onClose }: Props) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAccessVehicleDetail(vehicleId)

  return (
    <Dialog open={vehicleId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('accessControl.vehicleDetail.title')}</DialogTitle>
          <DialogDescription>
            {data ? (
              <span className="font-mono">
                {data.vehicle.plate_number_original || data.vehicle.plate_number_normalized}
              </span>
            ) : (
              ' '
            )}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <LoadingSpinner />}
        {isError && <p className="text-[13px] text-red">{t('common.error')}</p>}

        {data && (
          <div className="flex flex-col gap-5">
            <div className="grid grid-cols-2 gap-3">
              <Field
                label={t('accessControl.vehicles.brandModel')}
                value={[data.vehicle.brand, data.vehicle.model].filter(Boolean).join(' ') || '—'}
              />
              <Field label={t('accessControl.vehicles.color')} value={data.vehicle.color ?? '—'} />
              <Field
                label={t('accessControl.vehicles.class')}
                value={data.vehicle.vehicle_class ?? '—'}
              />
              <Field
                label={t('accessControl.vehicleDetail.country')}
                value={data.vehicle.plate_country ?? '—'}
              />
              <Field
                label={t('accessControl.columns.status')}
                value={<AccessStatusBadge status={data.vehicle.status} />}
              />
              {data.vehicle.blocked_reason && (
                <Field
                  label={t('accessControl.vehicleDetail.blockedReason')}
                  value={data.vehicle.blocked_reason}
                />
              )}
            </div>

            {/* Связи с квартирами */}
            <div className="flex flex-col gap-2">
              <h3 className="text-[12px] font-semibold uppercase tracking-wider text-text-secondary">
                {t('accessControl.vehicleDetail.apartments')}
              </h3>
              {data.apartments.length === 0 ? (
                <p className="text-[13px] text-text-muted">—</p>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {data.apartments.map((a) => (
                    <div
                      key={`${a.apartment_id}-${a.relation_type}`}
                      className="flex items-center gap-2 rounded-sm border border-border-default bg-bg-surface px-3 py-2 text-[12px]"
                    >
                      <span className="text-text-primary">
                        {t('accessControl.vehicleDetail.apartment')} #{a.apartment_id}
                      </span>
                      <span className="text-text-muted">{a.relation_type}</span>
                      <span className="ml-auto">
                        <AccessStatusBadge status={a.status} />
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Последние события */}
            <div className="flex flex-col gap-2">
              <h3 className="text-[12px] font-semibold uppercase tracking-wider text-text-secondary">
                {t('accessControl.vehicleDetail.recentEvents')}
              </h3>
              {data.recent_events.length === 0 ? (
                <p className="text-[13px] text-text-muted">—</p>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {data.recent_events.map((e) => (
                    <div
                      key={e.id}
                      className="flex items-center gap-2 rounded-sm border border-border-default bg-bg-surface px-3 py-2 text-[12px]"
                    >
                      <DecisionBadge decision={e.decision} />
                      <span className="text-text-muted">
                        {t(`accessControl.direction.${e.direction}`, { defaultValue: e.direction })}
                      </span>
                      <span className="ml-auto text-text-muted">
                        {formatDateTime(e.captured_at)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
