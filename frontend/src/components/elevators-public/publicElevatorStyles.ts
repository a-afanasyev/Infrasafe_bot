import type { ElevatorStatus } from '../../types/elevators'
import type { PublicElevatorsSummary } from '../../hooks/usePublicElevators'

// Общее оформление публичных экранов лифтов — сводка на табло (T16/T17) и
// страница /elevators (T17). Стиль Resident Board (inline-стили, Nunito/#f7f5f0):
// cardStyle/headerStyle/titleStyle — та же осознанная дубликация литералов,
// что у WorkReportsModule.tsx / WorkReportsArchivePage.tsx (инертный CSS).

export const cardStyle: React.CSSProperties = { background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }
export const headerStyle: React.CSSProperties = { padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', background: '#f0ede6' }
export const titleStyle: React.CSSProperties = { fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }
export const monoStyle: React.CSSProperties = { fontFamily: "'IBM Plex Mono',monospace" }
export const pillStyle: React.CSSProperties = { ...monoStyle, fontSize: '0.75rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, whiteSpace: 'nowrap' }

export interface StatusPalette {
  color: string
  bg: string
}

// Палитра ElevatorStatusBadge (green / red / orange / blue) в hex-цветах табло.
export const STATUS_STYLE: Record<ElevatorStatus, StatusPalette> = {
  working: { color: '#059669', bg: '#ecfdf5' },
  not_working: { color: '#dc2626', bg: '#fef2f2' },
  under_repair: { color: '#d97706', bg: '#fef9e7' },
  maintenance: { color: '#2563eb', bg: '#eff3ff' },
}
export const NEUTRAL_STYLE: StatusPalette = { color: '#6b7280', bg: '#f0ede6' }

export function statusStyle(status: ElevatorStatus): StatusPalette {
  return STATUS_STYLE[status] ?? NEUTRAL_STYLE
}

// «Проблемные» лифты — те, что житель хочет увидеть первыми: не работает / в ремонте
// (плановое ТО — не проблема).
export const PROBLEM_STATUSES: readonly ElevatorStatus[] = ['not_working', 'under_repair'] as const

export function isProblemStatus(status: ElevatorStatus): boolean {
  return PROBLEM_STATUSES.includes(status)
}

export const EMPTY_SUMMARY: PublicElevatorsSummary = Object.freeze({ total: 0, working: 0, not_working: 0, under_repair: 0, maintenance: 0 })

/** Левая рамка строки лифта: рабочий — нейтральная, любой другой статус — цвет статуса. */
export function rowBorderColor(status: ElevatorStatus): string {
  return status === 'working' ? 'rgba(0,0,0,0.12)' : statusStyle(status).color
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

// ISO datetime → "DD.MM.YYYY" по локальному времени; date-only строки
// (cert_valid_until и т.п.) идут через formatCompletedOn, не сюда.
export function formatSince(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.${d.getFullYear()}`
}

/** ISO datetime → "DD.MM" — короткая форма для строк сводки на табло. */
export function formatSinceShort(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}`
}

/** Unix-мс → "HH:MM" локального времени (индикатор «Данные актуальны на»). */
export function formatClock(ms: number): string {
  const d = new Date(ms)
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}
