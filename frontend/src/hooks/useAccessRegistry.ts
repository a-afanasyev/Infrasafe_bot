import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { accessClient } from '../api/accessClient'
import { safeErrorMessage } from '../utils/errorMessage'
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
  CreateVehiclePayload,
  UpdateVehicleStatusPayload,
  CreateTaxiPassPayload,
  ReviewRequestPayload,
  ReviewRequestResponse,
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

// ── Действия менеджера: мутации базы доступа ─────────────────────────────────
// Каждая мутация инвалидирует свой query-ключ (таблицы перезапрашиваются) и сама
// показывает toast успеха/ошибки (i18n). Дубль авто (409) → понятный текст.

/** HTTP-статус ответа ошибки (axios), если есть. */
function errorStatus(err: unknown): number | undefined {
  return axios.isAxiosError(err) ? err.response?.status : undefined
}

/** Создание авто менеджером (POST /vehicles). 409 → «авто уже существует». */
export function useCreateVehicle() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<VehicleRow, unknown, CreateVehiclePayload>({
    mutationFn: (payload) => accessClient.post('/vehicles', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-vehicles'] })
      toast.success(t('accessControl.actions.vehicleCreated'))
    },
    onError: (err) =>
      toast.error(
        errorStatus(err) === 409
          ? t('accessControl.actions.vehicleDuplicate')
          : safeErrorMessage(err, t('common.error')),
      ),
  })
}

/** Смена статуса авто (PATCH /vehicles/{id}/status): block/unblock/archive. */
export function useUpdateVehicleStatus() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<
    VehicleRow,
    unknown,
    { vehicleId: number; payload: UpdateVehicleStatusPayload }
  >({
    mutationFn: ({ vehicleId, payload }) =>
      accessClient.patch(`/vehicles/${vehicleId}/status`, payload).then((r) => r.data),
    onSuccess: (_data, { payload }) => {
      qc.invalidateQueries({ queryKey: ['access-vehicles'] })
      qc.invalidateQueries({ queryKey: ['access-vehicle-detail'] })
      const msg =
        payload.status === 'blocked'
          ? t('accessControl.actions.vehicleBlocked')
          : payload.status === 'archived'
            ? t('accessControl.actions.vehicleArchived')
            : t('accessControl.actions.vehicleUnblocked')
      toast.success(msg)
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

/** Создание taxi-пропуска (POST /passes/taxi). */
export function useCreateTaxiPass() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<PassRow, unknown, CreateTaxiPassPayload>({
    mutationFn: (payload) => accessClient.post('/passes/taxi', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-passes'] })
      toast.success(t('accessControl.actions.taxiPassCreated'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

/** Рассмотрение заявки жителя (POST /requests/{id}/review): approve/reject. */
export function useReviewRequest() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<
    ReviewRequestResponse,
    unknown,
    { requestId: number; payload: ReviewRequestPayload }
  >({
    mutationFn: ({ requestId, payload }) =>
      accessClient.post(`/requests/${requestId}/review`, payload).then((r) => r.data),
    onSuccess: (_data, { payload }) => {
      qc.invalidateQueries({ queryKey: ['access-requests'] })
      // approve может создать/привязать авто — обновляем и реестр авто.
      qc.invalidateQueries({ queryKey: ['access-vehicles'] })
      toast.success(
        payload.action === 'approve'
          ? t('accessControl.actions.requestApproved')
          : t('accessControl.actions.requestRejected'),
      )
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}
