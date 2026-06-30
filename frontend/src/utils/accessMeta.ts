import type { TFunction } from 'i18next'
import type { ApplicantInfo, AddressInfo, ZoneRef } from '../types/access'

/**
 * Форматтеры обогащённых деталей базы доступа (заявитель/адрес/зона). Чистые
 * функции — вынесены из AccessMeta.tsx, чтобы не ломать react-refresh.
 */

export function formatAddress(a: AddressInfo | null | undefined, t: TFunction): string {
  if (!a) return '—'
  const apt = a.apartment_number
    ? t('accessControl.meta.apt', { n: a.apartment_number })
    : null
  const parts = [a.yard_name, a.building_address, apt].filter(Boolean)
  return parts.length ? parts.join(' · ') : `#${a.apartment_id}`
}

export function formatApplicant(a: ApplicantInfo | null | undefined): string {
  if (!a) return '—'
  const contact = [a.phone, a.username ? `@${a.username}` : null].filter(Boolean).join(' · ')
  const name = a.name || `ID ${a.user_id}`
  return contact ? `${name} · ${contact}` : name
}

export function formatZones(zones: ZoneRef[] | null | undefined): string {
  if (!zones || zones.length === 0) return '—'
  return zones.map((z) => z.name || z.code || `#${z.id}`).join(', ')
}
