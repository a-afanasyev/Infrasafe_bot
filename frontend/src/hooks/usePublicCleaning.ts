import { useQuery } from '@tanstack/react-query'
import { publicClient } from '../api/publicClient'

// Открытая сводка уборки для жителей (GET /api/v2/public/cleaning/*): статусы и
// расписание без имён сотрудников. При выключенном модуле сводка отвечает
// `enabled: false` — блок на странице просто не показывается.

export type PublicCleaningState = 'done' | 'in_progress' | 'planned' | 'none'

export interface PublicCleaningEntrance {
  entrance: number
  state: 'done' | 'pending' | 'none'
  done_at: string | null
  photo_ids: number[]
}

export interface PublicCleaningHouse {
  building_id: number
  address: string
  state: PublicCleaningState
  done_at: string | null
  entrances: PublicCleaningEntrance[]
  /** Двор (фаза комплекса): по нему группируются плитки на главной. */
  yard_id?: number | null
  yard_name?: string | null
}

export interface PublicCleaningToday {
  enabled: boolean
  work_date: string
  buildings_total: number
  buildings_done: number
  buildings: PublicCleaningHouse[]
}

export interface PublicCleaningWork {
  work_kind: 'wet' | 'dry' | 'elevator' | 'parking' | 'fire_stairs'
  floor_from?: number
  floor_to?: number
  /** Только у работ не для всего дома (например, выход на парковку). */
  entrances?: number[]
}

export interface PublicCleaningBuilding {
  building_id: number
  address: string
  entrance_count: number
  work_date: string
  entrances: PublicCleaningEntrance[]
  week: PublicCleaningWork[][]
}

export function usePublicCleaningToday(enabled = true) {
  return useQuery<PublicCleaningToday>({
    queryKey: ['public-cleaning', 'today'],
    queryFn: () => publicClient.get('/api/v2/public/cleaning/today').then((r) => r.data),
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled,
  })
}

export function usePublicCleaningBuilding(buildingId: number | null) {
  return useQuery<PublicCleaningBuilding>({
    queryKey: ['public-cleaning', 'building', buildingId],
    queryFn: () => publicClient.get(`/api/v2/public/cleaning/buildings/${buildingId}`).then((r) => r.data),
    enabled: buildingId !== null,
    staleTime: 30_000,
    retry: false, // 404 — дом жителям не показывается
  })
}

/** Адрес открытого фото уборки (без кэша; скрытое фото — 404). По умолчанию — лёгкое превью
 *  для миниатюр, `original` — полный кадр для просмотра. */
export function publicCleaningPhotoUrl(photoId: number, original = false): string {
  return `${publicClient.defaults.baseURL ?? ''}/api/v2/public/cleaning/photos/${photoId}${original ? '?original=true' : ''}`
}
