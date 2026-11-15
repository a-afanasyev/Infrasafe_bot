import { useQuery } from '@tanstack/react-query'
import { twaClient } from '../twaClient'
import { useCurrentShift } from '../simple/api'

// Отключения от сантехника на смене — один серверный путь для бота, TWA и
// простого режима (uk_management_bot/services/notices/outages.py).
const BASE = '/api/v2/board-config/notices/outages'

export const OUTAGE_RESOURCES = ['water', 'heating'] as const
export type OutageResource = (typeof OUTAGE_RESOURCES)[number]
export const OUTAGE_DURATIONS = ['1h', '2h', '4h', 'day', 'unknown'] as const
export type OutageDuration = (typeof OUTAGE_DURATIONS)[number]

export interface OutageNotice {
  id: number
  resource: string | null
  title_ru: string
  title_uz: string
}

export interface OutageYard {
  id: number
  name: string
  buildings: { id: number; address: string }[]
}

export interface OutageOptions {
  /** Сантехник на смене; иначе `reason`: not_plumber | no_active_shift. */
  allowed: boolean
  reason: string | null
  yards: OutageYard[]
  /** Незакрытые отключения: сантехнику на смене — все, остальным — свои. */
  open: OutageNotice[]
}

export const OUTAGES_KEY = ['twa', 'outages'] as const

export function useOutageOptions() {
  // Ответ зависит от смены («сантехник на смене»): id смены — часть ключа, поэтому
  // «Начать» / «Закончить» перезапрашивают его сами. Без этого кнопка оставалась
  // неактивной после старта смены — экран показывал ответ, полученный до него.
  const shift = useCurrentShift()
  return useQuery<OutageOptions>({
    queryKey: [...OUTAGES_KEY, shift.data?.id ?? null],
    queryFn: () => twaClient.get(`${BASE}/options`).then((r) => r.data),
    enabled: !shift.isLoading,
    staleTime: 15_000,
  })
}

export interface OutageBody {
  resource: OutageResource
  building_ids: number[]
  duration: OutageDuration
}

export const announceOutage = (body: OutageBody) => twaClient.post(BASE, body).then((r) => r.data as OutageNotice)
export const closeOutage = (id: number) => twaClient.post(`${BASE}/${id}/close`).then((r) => r.data as OutageNotice)

/** Код отказа сервера (detail) → ключ фразы; незнакомый — общая ошибка. */
export function outageErrorKey(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  const known = ['already_open', 'no_active_shift', 'not_plumber', 'not_yours', 'not_open']
  return `twa.outage.error.${typeof detail === 'string' && known.includes(detail) ? detail : 'generic'}`
}
