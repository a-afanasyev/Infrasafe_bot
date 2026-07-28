import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type {
  ResidentListResponse,
  ResidentProfile,
  ResidentStats,
} from '../types/api'

export type ResidentFilters = {
  status?: string
  verification_status?: string
  yard_id?: number
  building_id?: number
  apartment_id?: number
}

// Раздел живёт на polling'е, а не на WS: события есть только у привязок к
// квартирам, а список и карточка зависят ещё и от статусов аккаунта и
// верификации, которые меняются в боте без событий. 30с — компромисс между
// «менеджер видит свежее» и нагрузкой.
const POLL_MS = 30_000

export function useResidents(
  filters: ResidentFilters = {},
  search?: string,
  page: { limit: number; offset: number } = { limit: 25, offset: 0 },
) {
  return useQuery<ResidentListResponse>({
    queryKey: ['residents', filters, search, page],
    queryFn: () =>
      apiClient
        .get('/api/v2/residents', {
          params: {
            ...filters,
            ...(search ? { q: search } : {}),
            limit: page.limit,
            offset: page.offset,
          },
        })
        .then(r => r.data),
    staleTime: 15_000,
    refetchInterval: POLL_MS,
  })
}

export function useResidentStats() {
  return useQuery<ResidentStats>({
    queryKey: ['residents-stats'],
    queryFn: () => apiClient.get('/api/v2/residents/stats').then(r => r.data),
    staleTime: 15_000,
    refetchInterval: POLL_MS,
  })
}

export function useResident(id: number | null) {
  return useQuery<ResidentProfile>({
    // Карточка тоже на polling'е: документы житель грузит ботом, и без
    // перезапроса менеджер не увидит их, пока не перезайдёт на страницу.
    queryKey: ['resident', id],
    queryFn: () => apiClient.get(`/api/v2/residents/${id}`).then(r => r.data),
    enabled: id !== null,
    refetchInterval: POLL_MS,
  })
}
