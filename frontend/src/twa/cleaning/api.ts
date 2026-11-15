import axios from 'axios'
import { useQuery } from '@tanstack/react-query'
import { twaClient } from '../twaClient'
import type { CleaningQueueItem, SendResult } from './queue'

/** API уборщицы (/api/v2/cleaning): задания на сегодня, сессия, фото точки. */
const BASE = '/api/v2/cleaning'
export const CLEANING_TASKS_KEY = ['twa', 'cleaning', 'tasks'] as const

export interface CleaningSlot {
  slot: string
  done: boolean
  photo_id: number | null
  captured_at: string | null
}

export interface CleaningMyTask {
  id: number
  building_id: number
  address: string
  entrance: number
  works: string[]
  status: string
  version: number
  session_open: boolean
  slots: CleaningSlot[]
}

export interface CleaningMyTasks {
  work_date: string
  day_end_at: string | null
  tasks: CleaningMyTask[]
}

export function useMyCleaningTasks() {
  return useQuery<CleaningMyTasks>({
    queryKey: CLEANING_TASKS_KEY,
    queryFn: () => twaClient.get(`${BASE}/my/tasks`).then((r) => r.data),
    staleTime: 15_000,
    // 403 — не уборщица, 404 — модуль выключен: раздел просто не показываем.
    retry: false,
  })
}

/** Первое онлайн-открытие задания. Без связи — молча: фото уйдут уровнем «offline». */
export function openCleaningSession(taskId: number): Promise<void> {
  return twaClient.post(`${BASE}/tasks/${taskId}/session`).then(() => undefined, () => undefined)
}

/** Отправка одной записи очереди; ключ операции = id записи. */
export async function sendCleaningPhoto(item: CleaningQueueItem): Promise<SendResult> {
  const form = new FormData()
  form.append('photo', item.photo, 'photo.jpg')
  form.append('slot', item.slot)
  form.append('op_key', item.id)
  form.append('captured_at', new Date(item.capturedAt).toISOString())
  form.append('source', item.source)
  try {
    const { data } = await twaClient.post(`${BASE}/tasks/${item.taskId}/photos`, form)
    return data.outcome === 'refused' ? { kind: 'final', reason: String(data.refusal_code) } : { kind: 'done' }
  } catch (err) {
    const status = axios.isAxiosError(err) ? err.response?.status : undefined
    const detail = axios.isAxiosError(err) ? String(err.response?.data?.detail ?? '') : ''
    // Нет ответа, 5xx, 429, «операция ещё идёт» — повторим тем же ключом.
    if (status === undefined || status >= 500 || status === 429 || detail === 'in_progress') return { kind: 'retry' }
    return { kind: 'final', reason: detail || 'bad_photo' }
  }
}

/** «floor:7» → 7; для точек вне этажей — null. */
export function floorOf(slot: string): number | null {
  return slot.startsWith('floor:') ? Number(slot.slice(6)) : null
}
