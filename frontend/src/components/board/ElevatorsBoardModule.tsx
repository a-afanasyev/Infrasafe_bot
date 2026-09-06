import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import {
  usePublicElevators,
  type PublicElevator,
  type PublicElevatorBuilding,
  type PublicElevatorYard,
  type PublicLang,
} from '../../hooks/usePublicElevators'
import { formatCompletedOn } from './formatCompletedOn'
import type { ElevatorStatus } from '../../types/elevators'

// T16 (Р16) — публичный виджет статусов лифтов на табло жителей: дома →
// подъезды → строки «Лифт N» со статус-пилюлей. Оформление — стиль Resident
// Board (inline-стили, Nunito/#f7f5f0), поэтому cardStyle/headerStyle/titleStyle
// — та же осознанная дубликация литералов, что и в WorkReportsModule.tsx.
// Пустой ответ НЕ прячет модуль (в отличие от ленты отчётов): превью в
// редакторе витрины должно быть видно — показываем заглушку.

const cardStyle: React.CSSProperties = { background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }
const headerStyle: React.CSSProperties = { padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', background: '#f0ede6' }
const titleStyle: React.CSSProperties = { fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }
const monoStyle: React.CSSProperties = { fontFamily: "'IBM Plex Mono',monospace" }

// Палитра ElevatorStatusBadge (green / red / orange / blue) в hex-цветах табло.
const STATUS_STYLE: Record<ElevatorStatus, { color: string; bg: string }> = {
  working: { color: '#059669', bg: '#ecfdf5' },
  not_working: { color: '#dc2626', bg: '#fef2f2' },
  under_repair: { color: '#d97706', bg: '#fef9e7' },
  maintenance: { color: '#2563eb', bg: '#eff3ff' },
}

// ISO datetime → "DD.MM.YYYY" по локальному времени; date-only строки
// (cert_valid_until и т.п.) идут через formatCompletedOn, не сюда.
function formatSince(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`
}

function groupByEntrance(elevators: PublicElevator[]): Array<{ entrance: number; elevators: PublicElevator[] }> {
  const groups: Array<{ entrance: number; elevators: PublicElevator[] }> = []
  for (const e of elevators) {
    const last = groups[groups.length - 1]
    if (last && last.entrance === e.entrance_number) groups[groups.length - 1] = { ...last, elevators: [...last.elevators, e] }
    else groups.push({ entrance: e.entrance_number, elevators: [e] })
  }
  return groups
}

function StatusPill({ status, t }: { status: ElevatorStatus; t: TFunction }) {
  const style = STATUS_STYLE[status] ?? { color: '#6b7280', bg: '#f0ede6' }
  return (
    <span
      data-testid="elevator-status-pill"
      data-status={status}
      style={{ ...monoStyle, fontSize: '0.72rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: style.bg, color: style.color, whiteSpace: 'nowrap' }}
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

// Свёрнутая строка «Обслуживает: {org} · {phone} · ТО {дата} · освид. до {дата} · доступность N %» —
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

function ElevatorRow({ e, t }: { e: PublicElevator; t: TFunction }) {
  const downtime = downtimeLine(e, t)
  const service = serviceLine(e, t)
  return (
    <div title={e.label} style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.06)', borderLeft: `3px solid ${(STATUS_STYLE[e.status] ?? { color: '#9ca3af' }).color}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#1a1a1a' }}>
          {t('board.elevators.elevator', { elevator: e.elevator_number })}
        </span>
        <StatusPill status={e.status} t={t} />
        {e.status_since && (
          <span style={{ ...monoStyle, fontSize: '0.72rem', color: '#9ca3af' }}>
            {t('board.elevators.since', { date: formatSince(e.status_since) })}
          </span>
        )}
      </div>
      {downtime && (
        <div style={{ fontSize: '0.82rem', color: '#b45309', marginTop: 6 }}>{downtime}</div>
      )}
      {service && (
        <div style={{ fontSize: '0.74rem', color: '#9ca3af', marginTop: 4 }}>{service}</div>
      )}
    </div>
  )
}

function BuildingBlock({ building, t }: { building: PublicElevatorBuilding; t: TFunction }) {
  return (
    <div>
      <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '0.95rem', marginBottom: 8 }}>
        {building.address}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
        {groupByEntrance(building.elevators).map((group) => (
          <div key={group.entrance}>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#6b7280', marginBottom: 6 }}>
              {t('board.elevators.entrance', { entrance: group.entrance })}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {group.elevators.map((e) => (
                <ElevatorRow key={`${e.entrance_number}-${e.elevator_number}`} e={e} t={t} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function YardBlock({ yard, showName, t }: { yard: PublicElevatorYard; showName: boolean; t: TFunction }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {showName && (
        <div style={{ ...monoStyle, fontSize: '0.75rem', fontWeight: 700, color: '#2563eb', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {yard.name}
        </div>
      )}
      {yard.buildings.map((b) => (
        <BuildingBlock key={b.id} building={b} t={t} />
      ))}
    </div>
  )
}

export interface ElevatorsBoardModuleProps {
  // ElevatorsCfg.title, уже локализованный вызывающим; пусто → i18n-дефолт.
  title?: string
}

// Данные читает сам (как остальные модули табло); заголовок — props'ом от
// ResidentBoardPage, у которого board-config (и configOverride редактора) уже есть.
export default function ElevatorsBoardModule({ title }: ElevatorsBoardModuleProps = {}) {
  const { t, i18n } = useTranslation()
  const lang: PublicLang = i18n.language?.startsWith('uz') ? 'uz' : 'ru'
  const { data } = usePublicElevators(lang)
  const yards = (data?.yards ?? []).filter((y) => y.buildings.some((b) => b.elevators.length > 0))
  const dispatchPhone = data?.dispatch_phone ?? null

  return (
    <div style={cardStyle}>
      <div style={{ ...headerStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={titleStyle}>{title || t('board.sections.elevators')}</div>
        {dispatchPhone && (
          <div style={{ ...monoStyle, fontSize: '0.75rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: '#eff3ff', color: '#2563eb' }}>
            {'\u{1F4DE}'} {t('board.elevators.dispatch')}: {dispatchPhone}
          </div>
        )}
      </div>
      <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {yards.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '14px 4px', color: '#9ca3af', fontSize: '0.9rem' }}>
            {t('board.elevators.empty')}
          </div>
        ) : (
          yards.map((yard) => <YardBlock key={yard.id} yard={yard} showName={yards.length > 1} t={t} />)
        )}
      </div>
    </div>
  )
}
