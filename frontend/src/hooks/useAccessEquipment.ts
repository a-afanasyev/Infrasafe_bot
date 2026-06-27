import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { accessClient } from '../api/accessClient'
import { safeErrorMessage } from '../utils/errorMessage'
import type {
  AccessPage,
  ZoneRow,
  CreateZonePayload,
  UpdateZonePayload,
  ZoneYardsPayload,
  ZoneYardsResponse,
  GateRow,
  CreateGatePayload,
  UpdateGatePayload,
  CameraRow,
  CreateCameraPayload,
  UpdateCameraPayload,
  BarrierRow,
  CreateBarrierPayload,
  UpdateBarrierPayload,
  ControllerRow,
  CreateControllerPayload,
  UpdateControllerPayload,
  ControllerCreateResponse,
  RotateKeyResponse,
  TestEventPayload,
  TestEventResponse,
} from '../types/access'

/**
 * React-Query хуки раздела «Оборудование» (управление точками въезда).
 * Источник — `accessClient` (baseURL .../api/v1/access), пути под `/admin/*`.
 *
 * RBAC бэкенда (registry.py / admin.py):
 *  - зоны, въезды — manager + system_admin;
 *  - камеры, шлагбаумы, контроллеры — ТОЛЬКО system_admin (manager → 403 на GET).
 * Гейтинг табов/действий выполняется на стороне страницы (useHasRole), а сами
 * запросы камер/шлагбаумов/контроллеров включаются только когда вкладка открыта.
 *
 * Каждая мутация инвалидирует свой query-ключ и сама показывает toast (i18n).
 * Дубль (409) → понятный текст «уже существует».
 */

const STALE_MS = 15_000

/** HTTP-статус ответа ошибки (axios), если есть. */
function errorStatus(err: unknown): number | undefined {
  return axios.isAxiosError(err) ? err.response?.status : undefined
}

// ── Зоны ──────────────────────────────────────────────────────────────────────
export function useAccessZones(enabled = true) {
  return useQuery<AccessPage<ZoneRow>>({
    queryKey: ['access-zones'],
    queryFn: () => accessClient.get('/admin/zones').then((r) => r.data),
    enabled,
    staleTime: STALE_MS,
  })
}

export function useCreateZone() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<ZoneRow, unknown, CreateZonePayload>({
    mutationFn: (payload) => accessClient.post('/admin/zones', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-zones'] })
      toast.success(t('accessControl.equipment.toast.zoneCreated'))
    },
    onError: (err) =>
      toast.error(
        errorStatus(err) === 409
          ? t('accessControl.equipment.toast.duplicate')
          : safeErrorMessage(err, t('common.error')),
      ),
  })
}

export function useUpdateZone() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<ZoneRow, unknown, { id: number; payload: UpdateZonePayload }>({
    mutationFn: ({ id, payload }) =>
      accessClient.patch(`/admin/zones/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-zones'] })
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

/** Привязка/отвязка фаз (yards) к зоне: POST /admin/zones/{id}/yards. */
export function useUpdateZoneYards() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<ZoneYardsResponse, unknown, { id: number; payload: ZoneYardsPayload }>({
    mutationFn: ({ id, payload }) =>
      accessClient.post(`/admin/zones/${id}/yards`, payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-zones'] })
      toast.success(t('accessControl.equipment.toast.yardsSaved'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

// ── Въезды (точки проезда) ──────────────────────────────────────────────────
export function useAccessGates(enabled = true) {
  return useQuery<AccessPage<GateRow>>({
    queryKey: ['access-gates'],
    queryFn: () => accessClient.get('/admin/gates').then((r) => r.data),
    enabled,
    staleTime: STALE_MS,
  })
}

export function useCreateGate() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<GateRow, unknown, CreateGatePayload>({
    mutationFn: (payload) => accessClient.post('/admin/gates', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-gates'] })
      toast.success(t('accessControl.equipment.toast.gateCreated'))
    },
    onError: (err) =>
      toast.error(
        errorStatus(err) === 409
          ? t('accessControl.equipment.toast.duplicate')
          : safeErrorMessage(err, t('common.error')),
      ),
  })
}

export function useUpdateGate() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<GateRow, unknown, { id: number; payload: UpdateGatePayload }>({
    mutationFn: ({ id, payload }) =>
      accessClient.patch(`/admin/gates/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-gates'] })
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

// ── Камеры (только system_admin) ─────────────────────────────────────────────
export function useAccessCameras(enabled = true) {
  return useQuery<AccessPage<CameraRow>>({
    queryKey: ['access-cameras'],
    queryFn: () => accessClient.get('/admin/cameras').then((r) => r.data),
    enabled,
    staleTime: STALE_MS,
  })
}

export function useCreateCamera() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<CameraRow, unknown, CreateCameraPayload>({
    mutationFn: (payload) => accessClient.post('/admin/cameras', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-cameras'] })
      toast.success(t('accessControl.equipment.toast.cameraCreated'))
    },
    onError: (err) =>
      toast.error(
        errorStatus(err) === 409
          ? t('accessControl.equipment.toast.duplicate')
          : safeErrorMessage(err, t('common.error')),
      ),
  })
}

export function useUpdateCamera() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<CameraRow, unknown, { id: number; payload: UpdateCameraPayload }>({
    mutationFn: ({ id, payload }) =>
      accessClient.patch(`/admin/cameras/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-cameras'] })
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

// ── Шлагбаумы (только system_admin) ──────────────────────────────────────────
export function useAccessBarriers(enabled = true) {
  return useQuery<AccessPage<BarrierRow>>({
    queryKey: ['access-barriers'],
    queryFn: () => accessClient.get('/admin/barriers').then((r) => r.data),
    enabled,
    staleTime: STALE_MS,
  })
}

export function useCreateBarrier() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<BarrierRow, unknown, CreateBarrierPayload>({
    mutationFn: (payload) => accessClient.post('/admin/barriers', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-barriers'] })
      toast.success(t('accessControl.equipment.toast.barrierCreated'))
    },
    onError: (err) =>
      toast.error(
        errorStatus(err) === 409
          ? t('accessControl.equipment.toast.duplicate')
          : safeErrorMessage(err, t('common.error')),
      ),
  })
}

export function useUpdateBarrier() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<BarrierRow, unknown, { id: number; payload: UpdateBarrierPayload }>({
    mutationFn: ({ id, payload }) =>
      accessClient.patch(`/admin/barriers/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-barriers'] })
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

// ── Контроллеры (только system_admin) ────────────────────────────────────────
export function useAccessControllers(enabled = true) {
  return useQuery<AccessPage<ControllerRow>>({
    queryKey: ['access-controllers'],
    queryFn: () => accessClient.get('/admin/controllers').then((r) => r.data),
    enabled,
    staleTime: STALE_MS,
  })
}

/** Создание контроллера. Ответ содержит api_key (PLAINTEXT, показать один раз). */
export function useCreateController() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<ControllerCreateResponse, unknown, CreateControllerPayload>({
    mutationFn: (payload) => accessClient.post('/admin/controllers', payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-controllers'] })
      toast.success(t('accessControl.equipment.toast.controllerCreated'))
    },
    onError: (err) =>
      toast.error(
        errorStatus(err) === 409
          ? t('accessControl.equipment.toast.duplicate')
          : safeErrorMessage(err, t('common.error')),
      ),
  })
}

export function useUpdateController() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<ControllerRow, unknown, { id: number; payload: UpdateControllerPayload }>({
    mutationFn: ({ id, payload }) =>
      accessClient.patch(`/admin/controllers/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-controllers'] })
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

/** Ротация ключа контроллера. Ответ — новый api_key (показать один раз). */
export function useRotateControllerKey() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<RotateKeyResponse, unknown, { id: number }>({
    mutationFn: ({ id }) =>
      accessClient.post(`/admin/controllers/${id}/rotate-key`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-controllers'] })
      toast.success(t('accessControl.equipment.toast.keyRotated'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

/**
 * Диагностический прогон точки въезда: POST /admin/controllers/{id}/test-event.
 * Бэкенд прогоняет синтетический ANPR через Decision Engine; событие появляется
 * и в истории проездов, и в live-ленте охраны — поэтому инвалидируем их кэши.
 * Результат (decision/команда) возвращается вызывающему (показ в том же диалоге);
 * тост — только при ошибке.
 */
export function useTestControllerEvent() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation<TestEventResponse, unknown, { id: number; payload: TestEventPayload }>({
    mutationFn: ({ id, payload }) =>
      accessClient.post(`/admin/controllers/${id}/test-event`, payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['access-events'] })
      qc.invalidateQueries({ queryKey: ['access-passes'] })
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}
