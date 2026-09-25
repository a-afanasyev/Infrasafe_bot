import { useQuery } from '@tanstack/react-query'
import { twaClient } from '../twaClient'
import type { TwaRequest } from '../types'
import type { QueueItem } from './queue/types'

/** Плитка вкладки «Взять» (GET /api/v2/requests/pool, схема PoolItem). */
export interface PoolItem {
  request_number: string
  status: string
  category: string
  urgency?: string | null
  description_first_line?: string | null
  address?: string | null
  address_type?: string | null
  building_address?: string | null
  entrance?: number | null
  floor?: number | null
  apartment_number?: string | null
  photo_media_id?: number | null
  created_at?: string | null
}

export interface PoolResponse {
  on_shift: boolean
  items: PoolItem[]
}

export interface CurrentShift {
  id: number
  start_time: string
}

/**
 * Шаблоны «Проблемы» — ровно Literal из ProblemBody (api/requests/schemas.py).
 * `other` — проблема своими словами, текст обязателен (иначе 422).
 */
export const PROBLEM_TEMPLATES = ['no_material', 'not_let_in', 'resident_absent', 'need_master', 'other'] as const
export type ProblemTemplate = (typeof PROBLEM_TEMPLATES)[number]

// Фото уходит по мобильной сети — даём запас больше edge-бюджета, но не
// бесконечно: зависший запрос не должен держать очередь.
const COMPLETE_TIMEOUT_MS = 60_000

export function usePool() {
  return useQuery<PoolResponse>({
    queryKey: ['twa', 'simple', 'pool'],
    queryFn: () => twaClient.get('/api/v2/requests/pool').then((r) => r.data),
    staleTime: 15_000,
  })
}

/** Тот же ключ и эндпоинт, что у pages/executor/ShiftPage — общий кэш. */
export function useCurrentShift() {
  return useQuery<CurrentShift | null>({
    queryKey: ['twa', 'current-shift'],
    queryFn: () => twaClient.get('/api/v2/executor/shifts/current').then((r) => r.data),
    refetchInterval: 30_000,
  })
}

/** Карточка заявки; ключ — как у pages/executor/TaskDetailPage (общий кэш). */
export function useTaskCard(number: string) {
  return useQuery<TwaRequest>({
    queryKey: ['twa', 'request', number],
    queryFn: () => twaClient.get(`/api/v2/requests/${encodeURIComponent(number)}`).then((r) => r.data),
    enabled: !!number,
  })
}

export function sendCompletion(item: QueueItem): Promise<unknown> {
  const form = new FormData()
  form.append('photo', new File([item.photo], item.fileName, { type: item.photo.type || 'image/jpeg' }))
  form.append('idempotency_key', item.idempotencyKey)
  return twaClient.post(`/api/v2/requests/${encodeURIComponent(item.requestNumber)}/complete`, form, {
    timeout: COMPLETE_TIMEOUT_MS,
  })
}

export function claimRequest(number: string): Promise<unknown> {
  return twaClient.post(`/api/v2/requests/${encodeURIComponent(number)}/claim`)
}

export function reportProblem(number: string, template: ProblemTemplate, text?: string): Promise<unknown> {
  const trimmed = text?.trim()
  return twaClient.post(`/api/v2/requests/${encodeURIComponent(number)}/problem`, {
    template,
    ...(trimmed ? { text: trimmed } : {}),
  })
}
