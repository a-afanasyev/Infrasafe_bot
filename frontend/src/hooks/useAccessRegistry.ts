import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { accessClient } from '../api/accessClient'
import type {
  AccessPage,
  AccessEventRow,
  AccessEventsFilters,
  AccessEventDetail,
  VehicleRow,
  VehiclesFilters,
  VehicleDetail,
  PassRow,
  PassesFilters,
  AccessRequestRow,
  AccessRequestsFilters,
  ResolvePayload,
  ResolveResponse,
  ManualOpenResponse,
} from '../types/access'

/**
 * React-Query хуки реестра контроля доступа (READ) + действия охраны (mutations).
 * Источник — `accessClient` (отдельный инстанс, baseURL = .../api/v1/access).
 *
 * Конверт списков `{items,total,limit,offset}` отдаётся как есть — пагинация
 * (limit/offset/total) живёт в вызывающем компоненте.
 */

const STALE_MS = 15_000

// Сбрасываем undefined-фильтры, чтобы не слать пустые query-параметры.
function cleanParams<T extends object>(filters: T): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

// ── События / история проездов ──────────────────────────────────────────────
export function useAccessEvents(filters: AccessEventsFilters = {}) {
  return useQuery<AccessPage<AccessEventRow>>({
    queryKey: ['access-events', filters],
    queryFn: () =>
      accessClient.get('/events', { params: cleanParams(filters) }).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useAccessEventDetail(eventId: number | null) {
  return useQuery<AccessEventDetail>({
    queryKey: ['access-event-detail', eventId],
    queryFn: () => accessClient.get(`/events/${eventId}`).then((r) => r.data),
    enabled: eventId !== null,
    staleTime: STALE_MS,
  })
}

// ── Авто ────────────────────────────────────────────────────────────────────
export function useAccessVehicles(filters: VehiclesFilters = {}) {
  return useQuery<AccessPage<VehicleRow>>({
    queryKey: ['access-vehicles', filters],
    queryFn: () =>
      accessClient.get('/vehicles', { params: cleanParams(filters) }).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useAccessVehicleDetail(vehicleId: number | null) {
  return useQuery<VehicleDetail>({
    queryKey: ['access-vehicle-detail', vehicleId],
    queryFn: () => accessClient.get(`/vehicles/${vehicleId}`).then((r) => r.data),
    enabled: vehicleId !== null,
    staleTime: STALE_MS,
  })
}

// ── Пропуска ────────────────────────────────────────────────────────────────
export function useAccessPasses(filters: PassesFilters = {}) {
  return useQuery<AccessPage<PassRow>>({
    queryKey: ['access-passes', filters],
    queryFn: () =>
      accessClient.get('/passes', { params: cleanParams(filters) }).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

// ── Заявки ──────────────────────────────────────────────────────────────────
export function useAccessRequests(filters: AccessRequestsFilters = {}) {
  return useQuery<AccessPage<AccessRequestRow>>({
    queryKey: ['access-requests', filters],
    queryFn: () =>
      accessClient.get('/requests', { params: cleanParams(filters) }).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

// ── Действия охраны (резолюция события manual_review) ────────────────────────
export function useResolveEvent() {
  const qc = useQueryClient()
  return useMutation<ResolveResponse, unknown, { eventId: string; payload: ResolvePayload }>({
    mutationFn: ({ eventId, payload }) =>
      accessClient.post(`/events/${eventId}/resolve`, payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-events'] })
    },
  })
}

export function useManualOpenBarrier() {
  return useMutation<ManualOpenResponse, unknown, { barrierId: number; reason: string }>({
    mutationFn: ({ barrierId, reason }) =>
      accessClient
        .post(`/barriers/${barrierId}/manual-open`, { reason })
        .then((r) => r.data),
  })
}
