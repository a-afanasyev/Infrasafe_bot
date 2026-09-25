import type { TFunction } from 'i18next'
import { URGENCY_MAP, type ApiUrgency } from '../../i18n/apiMaps'
import type { TwaRequest } from '../types'
import type { PoolItem } from './api'

/** Состояние плитки глазами исполнителя — три значения вместо девяти статусов. */
export type TileState = 'inWork' | 'returned' | 'pending'

// Срочность — через URGENCY_MAP: он принимает и канон-ключ, и legacy-рус.
function urgencyKey(urgency: string | null | undefined): string | null {
  return urgency ? (URGENCY_MAP[urgency as ApiUrgency] ?? null) : null
}

export function isUrgent(urgency: string | null | undefined): boolean {
  const key = urgencyKey(urgency)
  return key === 'urgency.urgent' || key === 'urgency.critical'
}

const STRIP_CLASS: Record<string, string> = {
  'urgency.critical': 'bg-red-600',
  'urgency.urgent': 'bg-orange-500',
  'urgency.medium': 'bg-yellow-400',
}

/** Цвет полосы срочности; null — полосы нет (обычная). */
export function urgencyStripClass(urgency: string | null | undefined): string | null {
  const key = urgencyKey(urgency)
  return key ? (STRIP_CLASS[key] ?? null) : null
}

/**
 * «Готово» (EXECUTOR_COMPLETE) канон допускает только из «В работе».
 * «Возвращена» решает менеджер (возвращает в работу), поэтому для неё и
 * прочих статусов вместо «Готово» — плашка «Ждёт менеджера».
 */
export function canComplete(status: string | null | undefined): boolean {
  return status === 'В работе'
}

export function tileState(task: TwaRequest, pending: ReadonlySet<string>): TileState {
  if (pending.has(task.request_number)) return 'pending'
  return task.status === 'Возвращена' ? 'returned' : 'inWork'
}

/** Причина возврата: житель (return_reason) или менеджер (manager_return_reason). */
export function returnReason(task: Pick<TwaRequest, 'return_reason' | 'manager_return_reason'>): string | null {
  return task.return_reason?.trim() || task.manager_return_reason?.trim() || null
}

function time(iso: string | null | undefined): number {
  const ms = iso ? Date.parse(iso) : NaN
  return Number.isNaN(ms) ? Number.MAX_SAFE_INTEGER : ms
}

const STATE_RANK: Record<TileState, number> = { returned: 0, inWork: 1, pending: 2 }

/**
 * Порядок «Мои»: вернули → срочные → по времени (старые первыми — дольше
 * ждут). «Ждёт отправки» — в конце: работа сделана, осталось доставить фото.
 */
export function sortMine(tasks: readonly TwaRequest[], pending: ReadonlySet<string>): TwaRequest[] {
  return [...tasks].sort((a, b) => {
    const byState = STATE_RANK[tileState(a, pending)] - STATE_RANK[tileState(b, pending)]
    if (byState !== 0) return byState
    const byUrgency = Number(isUrgent(b.urgency)) - Number(isUrgent(a.urgency))
    if (byUrgency !== 0) return byUrgency
    return time(a.created_at) - time(b.created_at)
  })
}

/** Первая непустая строка текста — одна строка на плитке. */
export function firstLine(text: string | null | undefined): string {
  return (text ?? '').split('\n').map((s) => s.trim()).find(Boolean) ?? ''
}

/**
 * Адрес плитки пула: «дом · подъезд · кв», если заявка привязана к
 * квартире; иначе строка адреса с сервера (уже на языке пользователя).
 */
export function poolAddress(item: PoolItem, t: TFunction): string {
  const parts = [
    item.building_address?.trim(),
    item.entrance != null ? t('twa.simple.address.entrance', { value: item.entrance }) : null,
    item.apartment_number ? t('twa.simple.address.apartment', { value: item.apartment_number }) : null,
  ].filter(Boolean)
  if (item.building_address && parts.length > 0) return parts.join(' · ')
  return item.address?.trim() ?? ''
}
