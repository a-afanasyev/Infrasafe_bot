import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { accessClient } from '../api/accessClient'
import { safeErrorMessage } from '../utils/errorMessage'
import type {
  AccessPage,
  SpotRow,
  SpotsFilters,
  CreateSpotPayload,
  UpdateSpotPayload,
  AssignmentRow,
  AssignmentsFilters,
  CreateAssignmentPayload,
  UpdateAssignmentPayload,
  ZoneOccupancy,
} from '../types/access'

/**
 * React-Query хуки управления парковкой (§14.2 пилот): места (parking_spots),
 * закрепления мест за квартирами (spot_assignments) и занятость зоны.
 *
 * Источник — `accessClient` (baseURL .../api/v1/access), пути под `/admin/*`.
 * RBAC бэкенда: manager + system_admin (как зоны/въезды).
 *
 * Каждая мутация инвалидирует свой query-ключ и сама показывает toast (i18n).
 * Дубль (409) → понятный текст «уже существует».
 */

const STALE_MS = 15_000

/** HTTP-статус ответа ошибки (axios), если есть. */
function errorStatus(err: unknown): number | undefined {
  return axios.isAxiosError(err) ? err.response?.status : undefined
}

/** Сериализуемые параметры запроса (без undefined-полей). */
function cleanParams<T extends Record<string, unknown>>(filters?: T): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  if (!filters) return out
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

// ── Места (parking_spots) ─────────────────────────────────────────────────────
export function useAccessSpots(filters?: SpotsFilters, enabled = true) {
  return useQuery<AccessPage<SpotRow>>({
    queryKey: ['access-spots', filters ?? {}],
    queryFn: () =>
      accessClient.get('/admin/spots', { params: cleanParams(filters) }).then((r) => r.data),
    enabled,
    staleTime: STALE_MS,
  })
}

export function useCreateSpot() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<SpotRow, unknown, CreateSpotPayload>({
    mutationFn: (payload) => accessClient.post('/admin/spots', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-spots'] })
      toast.success(t('accessControl.parking.toast.spotCreated'))
    },
    onError: (err) =>
      toast.error(
        errorStatus(err) === 409
          ? t('accessControl.equipment.toast.duplicate')
          : safeErrorMessage(err, t('common.error')),
      ),
  })
}

export function useUpdateSpot() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<SpotRow, unknown, { id: number; payload: UpdateSpotPayload }>({
    mutationFn: ({ id, payload }) =>
      accessClient.patch(`/admin/spots/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-spots'] })
      toast.success(t('accessControl.equipment.toast.saved'))
    },
    onError: (err) =>
      toast.error(
        errorStatus(err) === 409
          ? t('accessControl.equipment.toast.duplicate')
          : safeErrorMessage(err, t('common.error')),
      ),
  })
}

// ── Закрепления мест (spot_assignments) ───────────────────────────────────────
export function useAccessSpotAssignments(filters?: AssignmentsFilters, enabled = true) {
  return useQuery<AccessPage<AssignmentRow>>({
    queryKey: ['access-spot-assignments', filters ?? {}],
    queryFn: () =>
      accessClient
        .get('/admin/spot-assignments', { params: cleanParams(filters) })
        .then((r) => r.data),
    enabled,
    staleTime: STALE_MS,
  })
}

export function useCreateSpotAssignment() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<AssignmentRow, unknown, CreateAssignmentPayload>({
    mutationFn: (payload) =>
      accessClient.post('/admin/spot-assignments', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-spot-assignments'] })
      toast.success(t('accessControl.parking.toast.assignmentCreated'))
    },
    onError: (err) =>
      toast.error(
        errorStatus(err) === 409
          ? t('accessControl.equipment.toast.duplicate')
          : safeErrorMessage(err, t('common.error')),
      ),
  })
}

/**
 * PATCH /admin/spot-assignments/{id}. Используется для «Отозвать»
 * (status=revoked) и «Продлить» (valid_until). Текст тоста зависит от тела.
 */
export function useUpdateSpotAssignment() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<AssignmentRow, unknown, { id: number; payload: UpdateAssignmentPayload }>({
    mutationFn: ({ id, payload }) =>
      accessClient.patch(`/admin/spot-assignments/${id}`, payload).then((r) => r.data),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['access-spot-assignments'] })
      const msg =
        vars.payload.status === 'revoked'
          ? t('accessControl.parking.toast.assignmentRevoked')
          : t('accessControl.equipment.toast.saved')
      toast.success(msg)
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

// ── Занятость зоны (occupancy) ────────────────────────────────────────────────
/** GET /admin/zones/{id}/occupancy. Включается только для shared-зон. */
export function useZoneOccupancy(zoneId: number, enabled = true) {
  return useQuery<ZoneOccupancy>({
    queryKey: ['access-zone-occupancy', zoneId],
    queryFn: () => accessClient.get(`/admin/zones/${zoneId}/occupancy`).then((r) => r.data),
    enabled,
    staleTime: STALE_MS,
  })
}
