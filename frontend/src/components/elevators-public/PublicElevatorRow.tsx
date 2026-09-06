import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import type { PublicElevator } from '../../hooks/usePublicElevators'
import type { ElevatorStatus } from '../../types/elevators'
import { formatCompletedOn } from '../board/formatCompletedOn'
import { formatSince, monoStyle, rowBorderColor, statusStyle } from './publicElevatorStyles'

// Строка одного лифта на публичной странице /elevators (в T16 жила в
// ElevatorsBoardModule): статус-пилюля, «с даты», причина простоя/запчасть при
// наличии, свёрнутая строка обслуживания. Левая рамка — цвет статуса (в т.ч.
// синий у ТО), у рабочих — нейтральная.

export function StatusPill({ status }: { status: ElevatorStatus }) {
  const { t } = useTranslation()
  const palette = statusStyle(status)
  return (
    <span
      data-testid="elevator-status-pill"
      data-status={status}
      style={{ ...monoStyle, fontSize: '0.72rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: palette.bg, color: palette.color, whiteSpace: 'nowrap' }}
    >
      {t(`elevators.status.${status}`)}
    </span>
  )
}

// Детали простоя приходят только при publish_downtime_details — иначе оба null.
function downtimeLine(e: PublicElevator, t: TFunction): string {
  const parts: string[] = []
  if (e.downtime_reason) parts.push(t('board.elevators.downtimeReason', { reason: e.downtime_reason }))
  if (e.spare_part_expected_on) parts.push(t('board.elevators.sparePartExpected', { date: formatCompletedOn(e.spare_part_expected_on) }))
  return parts.join(' · ')
}

// «Обслуживает: {org} · {phone} · ТО {дата} · освид. до {дата} · доступность N %» —
// только заполненные части.
function serviceLine(e: PublicElevator, t: TFunction): string {
  const parts: string[] = []
  if (e.service_org_name) parts.push(t('board.elevators.servicedBy', { org: e.service_org_name }))
  if (e.service_org_phone) parts.push(e.service_org_phone)
  if (e.last_maintenance_on) parts.push(t('board.elevators.lastMaintenance', { date: formatCompletedOn(e.last_maintenance_on) }))
  if (e.cert_valid_until) {
    parts.push(t('board.elevators.certUntil', { date: formatCompletedOn(e.cert_valid_until) }))
    if (e.cert_expired) parts.push(t('board.elevators.certExpired'))
  }
  if (e.availability_30d != null) parts.push(t('board.elevators.availability', { pct: Math.round(e.availability_30d * 100) }))
  return parts.join(' · ')
}

export default function PublicElevatorRow({ e }: { e: PublicElevator }) {
  const { t } = useTranslation()
  const downtime = downtimeLine(e, t)
  const service = serviceLine(e, t)
  return (
    <div
      data-testid="public-elevator-row"
      title={e.label}
      style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.06)', borderLeft: `3px solid ${rowBorderColor(e.status)}` }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#1a1a1a' }}>
          {t('board.elevators.elevator', { elevator: e.elevator_number })}
        </span>
        <StatusPill status={e.status} />
        {e.status_since && (
          <span style={{ ...monoStyle, fontSize: '0.72rem', color: '#9ca3af' }}>
            {t('board.elevators.since', { date: formatSince(e.status_since) })}
          </span>
        )}
      </div>
      {downtime && <div style={{ fontSize: '0.82rem', color: '#b45309', marginTop: 6 }}>{downtime}</div>}
      {service && <div style={{ fontSize: '0.74rem', color: '#9ca3af', marginTop: 4 }}>{service}</div>}
    </div>
  )
}
