import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '../utils/errorMessage'
import type {
  CleaningBuilding,
  CleaningComplaint,
  CleaningPlan,
  CleaningPlanItem,
  CleaningPlanView,
  CleaningRules,
  CleaningStaff,
  CleaningTaskCard,
  CleaningTasks,
  CleaningTimesheetRow,
} from '../types/cleaning'

/**
 * Раздел менеджера «Уборка» (/api/v2/cleaning): план дома, привязка подъездов,
 * нагрузка, настройки. Правки плана и привязки действуют с завтра — поэтому
 * после сохранения перечитываем всё, что показывает «как будет».
 */
export const CLEANING_BASE = '/api/v2/cleaning'
const STALE_MS = 30_000

export const cleaningKeys = {
  all: ['cleaning'] as const,
  buildings: ['cleaning', 'buildings'] as const,
  plan: (buildingId: number) => ['cleaning', 'plan', buildingId] as const,
  staff: ['cleaning', 'staff'] as const,
  rules: ['cleaning', 'rules'] as const,
}

export function useCleaningBuildings() {
  return useQuery<CleaningBuilding[]>({
    queryKey: cleaningKeys.buildings,
    queryFn: () => apiClient.get(`${CLEANING_BASE}/buildings`).then((r) => r.data.buildings),
    staleTime: STALE_MS,
  })
}

export function useCleaningPlan(buildingId: number | null) {
  return useQuery<CleaningPlanView>({
    queryKey: cleaningKeys.plan(buildingId ?? 0),
    queryFn: () => apiClient.get(`${CLEANING_BASE}/buildings/${buildingId}/plan`).then((r) => r.data),
    enabled: buildingId !== null,
    staleTime: STALE_MS,
  })
}

export function useCleaningStaff() {
  return useQuery<CleaningStaff>({
    queryKey: cleaningKeys.staff,
    queryFn: () => apiClient.get(`${CLEANING_BASE}/staff`).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useCleaningRules() {
  return useQuery<CleaningRules>({
    queryKey: cleaningKeys.rules,
    queryFn: () => apiClient.get(`${CLEANING_BASE}/rules`).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

/** Общая обвязка мутаций раздела: перечитать раздел, тост об успехе или ошибке. */
function useCleaningMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>, successKey: string) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cleaningKeys.all })
      toast.success(t(successKey))
    },
    onError: (err) => {
      // Отказ часто значит «на экране устаревшее» (stale): перечитать, иначе повтор упрётся в то же.
      queryClient.invalidateQueries({ queryKey: cleaningKeys.all })
      const detail = safeErrorMessage(err, t('common.error'))
      const code = detail.split(':')[0]
      toast.error(/^[a-z_]+$/.test(code) ? t(`cleaning.errors.${code}`, { defaultValue: detail }) : detail)
    },
  })
}

export function useSaveCleaningPlan(buildingId: number) {
  return useCleaningMutation(
    (body: { items: CleaningPlanItem[]; extra_points: string[] }) =>
      apiClient.put(`${CLEANING_BASE}/buildings/${buildingId}/plan`, body).then((r) => r.data as CleaningPlan),
    'cleaning.toast.planSaved',
  )
}

export function useSaveCleaningSettings(buildingId: number) {
  return useCleaningMutation(
    (body: { show_to_residents: boolean; show_photos: boolean }) =>
      apiClient.put(`${CLEANING_BASE}/buildings/${buildingId}/settings`, body).then((r) => r.data),
    'cleaning.toast.settingsSaved',
  )
}

export function useAssignCleaner() {
  return useCleaningMutation(
    (body: { building_id: number; entrances: number[] | null; user_id: number | null }) =>
      apiClient.put(`${CLEANING_BASE}/assignments`, body).then((r) => r.data),
    'cleaning.toast.assigned',
  )
}

export function useSaveCleaningRules() {
  return useCleaningMutation(
    (patch: Record<string, string | number | boolean>) =>
      apiClient.put(`${CLEANING_BASE}/rules`, patch).then((r) => r.data as CleaningRules),
    'cleaning.toast.rulesSaved',
  )
}

// ── контроль ────────────────────────────────────────────────────────────────

export const CONTROL_BASE = `${CLEANING_BASE}/control`
// Уборщица снимает, пока менеджер смотрит: без опроса карточка показывала бы прошлый статус.
const LIVE_MS = 15_000

export function useCleaningTasks(dateFrom: string, dateTo: string, status?: string) {
  return useQuery<CleaningTasks>({
    queryKey: ['cleaning', 'tasks', dateFrom, dateTo, status ?? ''],
    refetchInterval: LIVE_MS,
    refetchOnWindowFocus: true,
    queryFn: () => apiClient
      .get(`${CONTROL_BASE}/tasks`, { params: { date_from: dateFrom, date_to: dateTo, ...(status ? { status } : {}) } })
      .then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useCleaningTaskCard(taskId: number) {
  return useQuery<CleaningTaskCard>({
    queryKey: ['cleaning', 'task', taskId],
    refetchInterval: LIVE_MS,
    refetchOnWindowFocus: true,
    queryFn: () => apiClient.get(`${CONTROL_BASE}/tasks/${taskId}`).then((r) => r.data),
    staleTime: STALE_MS,
  })
}

export function useCleaningComplaints(dateFrom: string, dateTo: string) {
  return useQuery<CleaningComplaint[]>({
    queryKey: ['cleaning', 'complaints', dateFrom, dateTo],
    refetchInterval: LIVE_MS,
    refetchOnWindowFocus: true,
    queryFn: () => apiClient
      .get(`${CONTROL_BASE}/complaints`, { params: { date_from: dateFrom, date_to: dateTo } })
      .then((r) => r.data.complaints),
    staleTime: STALE_MS,
  })
}

export function useCleaningTimesheet(dateFrom: string, dateTo: string) {
  return useQuery<CleaningTimesheetRow[]>({
    queryKey: ['cleaning', 'timesheet', dateFrom, dateTo],
    queryFn: () => apiClient
      .get(`${CONTROL_BASE}/timesheet`, { params: { date_from: dateFrom, date_to: dateTo } })
      .then((r) => r.data.rows),
    staleTime: STALE_MS,
  })
}

export function useDecideCleaningTask(taskId: number) {
  return useCleaningMutation(
    (body: { to: string; version: number; comment?: string }) =>
      apiClient.post(`${CONTROL_BASE}/tasks/${taskId}/decision`, body).then((r) => r.data),
    'cleaning.toast.decided',
  )
}

export function useReassignCleaningTask(taskId: number) {
  return useCleaningMutation(
    (userId: number) => apiClient.put(`${CONTROL_BASE}/tasks/${taskId}/responsible`, { user_id: userId }).then((r) => r.data),
    'cleaning.toast.reassigned',
  )
}

export function useDecideCleaningComplaint() {
  return useCleaningMutation(
    ({ id, outcome }: { id: number; outcome: 'confirmed' | 'unfounded' }) =>
      apiClient.post(`${CONTROL_BASE}/complaints/${id}/decision`, { outcome }).then((r) => r.data),
    'cleaning.toast.complaintDecided',
  )
}

/** Файл фото уборки как data: URL (CSP дашборда не пускает blob: в img-src). */
export function useCleaningPhotoUrl(photoId: number, enabled: boolean, original = false) {
  return useQuery<string>({
    queryKey: ['cleaning', 'photo', photoId, original],
    queryFn: async () => {
      // Сетка — лёгкие превью; оригинал качается, только когда фото открыли.
      const { data } = await apiClient.get(`${CONTROL_BASE}/photos/${photoId}/file`, {
        responseType: 'blob', params: original ? { original: true } : undefined,
      })
      return new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result))
        reader.onerror = () => reject(reader.error ?? new Error('read failed'))
        reader.readAsDataURL(data as Blob)
      })
    },
    enabled,
    staleTime: Infinity,
  })
}
