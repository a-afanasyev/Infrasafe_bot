import { useQuery } from '@tanstack/react-query'
// publicClient из api/publicClient.ts (withCredentials: false) — анонимный
// эндпоинт, см. naming-trap комментарий в обоих файлах.
import { publicClient } from '../api/publicClient'
import type { ElevatorStatus } from '../types/elevators'

// Публичный виджет статусов лифтов (GET /api/v2/public/elevators, T16/Р16).
// Зеркало PublicElevatorsOut бэкенда: ни id лифта, ни public_code, ни паспорта
// здесь нет и быть не должно.
export interface PublicElevator {
  entrance_number: number
  elevator_number: number
  label: string
  status: ElevatorStatus
  status_since: string | null
  availability_30d: number | null
  last_maintenance_on: string | null
  cert_valid_until: string | null
  cert_expired: boolean
  service_org_name: string | null
  service_org_phone: string | null
  manufacturer: string | null
  model: string | null
  production_year: number | null
  capacity_kg: number | null
  // Только при publish_downtime_details=True на карточке лифта, иначе null.
  downtime_reason: string | null
  spare_part_expected_on: string | null
}

export interface PublicElevatorBuilding {
  id: number
  address: string
  elevators: PublicElevator[]
}

export interface PublicElevatorYard {
  id: number
  name: string
  buildings: PublicElevatorBuilding[]
}

// Счётчики по статусам — по тем же лифтам, что и в `yards` (T17/Р17): табло
// показывает «N из M работают», страница /elevators — полный список.
export interface PublicElevatorsSummary {
  total: number
  working: number
  not_working: number
  under_repair: number
  maintenance: number
}

export interface PublicElevatorsData {
  yards: PublicElevatorYard[]
  // Опционально ради раскатки: фронт может уехать раньше API — старый ответ без
  // `summary` читается через summaryOf() (publicElevatorsFilter.ts), которая
  // досчитывает сводку по `yards`.
  summary?: PublicElevatorsSummary
  dispatch_phone: string | null
  generated_at: string
}

export type PublicLang = 'ru' | 'uz'

export interface UsePublicElevatorsOptions {
  // false — запрос не уходит (страница /elevators при выключенном флаге редиректит,
  // не дёргая API).
  enabled?: boolean
}

// Поллинг как у usePublicBoard — без WebSocket и без auth; подписи лифтов
// локализует бэкенд по ?lang, поэтому язык входит в ключ запроса.
export function usePublicElevators(lang: PublicLang, { enabled = true }: UsePublicElevatorsOptions = {}) {
  return useQuery<PublicElevatorsData>({
    queryKey: ['public-elevators', lang],
    queryFn: () =>
      publicClient.get('/api/v2/public/elevators', { params: { lang } }).then((r) => r.data),
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled,
  })
}
