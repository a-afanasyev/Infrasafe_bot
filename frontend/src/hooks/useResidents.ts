import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import i18n from '../i18n'
import { safeErrorMessage } from '@/utils/errorMessage'
import { apiClient } from '../api/client'
import { useWebSocket } from './useWebSocket'
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

// ── Мутации (PR-4) ───────────────────────────────────────────────────
//
// Инвалидируется ВЕСЬ набор кэшей, где те же данные видны с другой стороны:
//
//   ['residents'] / ['resident', id] / ['residents-stats'] — сам раздел;
//   ['moderation'] / ['address-stats'] — очередь заявок и плитка «Адресов»;
//   ['apartment-detail'] / ['apartments'] / ['all-apartments'] — карточка
//       квартиры показывает СПИСОК ЖИЛЬЦОВ, а таблицы квартир — их КОЛИЧЕСТВО;
//       и то и другое меняется от привязки и отвязки.
//
// Пропустишь один — менеджер увидит расхождение между экранами и не поймёт,
// какому верить. Ключи адресных кэшей параметризованы (id дома, фильтры),
// поэтому инвалидируются по префиксу — точный id знать неоткуда и не нужно.
function useResidentMutation<TArgs>(
  request: (args: TArgs) => Promise<unknown>,
  { successKey, errorKey, residentId }: {
    successKey: string
    errorKey: string
    residentId: number
  },
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      toast.success(i18n.t(successKey))
      for (const key of [
        ['residents'], ['resident', residentId], ['residents-stats'],
        ['moderation'], ['address-stats'],
        ['apartment-detail'], ['apartments'], ['all-apartments'],
      ]) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
    onError: (error: unknown) => {
      console.error(errorKey, error)
      toast.error(i18n.t(errorKey), {
        description: safeErrorMessage(error, i18n.t('common.error')),
      })
    },
  })
}

export function useApproveResident(id: number) {
  return useResidentMutation<{ comment?: string }>(
    body => apiClient.post(`/api/v2/residents/${id}/approve`, body).then(r => r.data),
    { successKey: 'residents.toast.approved', errorKey: 'residents.toast.approveFailed', residentId: id },
  )
}

export function useBlockResident(id: number) {
  return useResidentMutation<{ reason: string }>(
    body => apiClient.post(`/api/v2/residents/${id}/block`, body).then(r => r.data),
    { successKey: 'residents.toast.blocked', errorKey: 'residents.toast.blockFailed', residentId: id },
  )
}

export function useUnblockResident(id: number) {
  return useResidentMutation<void>(
    () => apiClient.post(`/api/v2/residents/${id}/unblock`).then(r => r.data),
    { successKey: 'residents.toast.unblocked', errorKey: 'residents.toast.unblockFailed', residentId: id },
  )
}

export function useAttachApartment(id: number) {
  return useResidentMutation<{ apartment_id: number; is_owner: boolean; is_primary: boolean }>(
    body => apiClient.post(`/api/v2/residents/${id}/apartments`, body).then(r => r.data),
    { successKey: 'residents.toast.attached', errorKey: 'residents.toast.attachFailed', residentId: id },
  )
}

export function useApproveBinding(id: number) {
  return useResidentMutation<{ uaId: number; comment?: string }>(
    ({ uaId, comment }) =>
      apiClient.post(`/api/v2/residents/${id}/apartments/${uaId}/approve`, { comment })
        .then(r => r.data),
    { successKey: 'residents.toast.bindingApproved', errorKey: 'residents.toast.bindingApproveFailed', residentId: id },
  )
}

export function useRejectBinding(id: number) {
  return useResidentMutation<{ uaId: number; comment: string }>(
    ({ uaId, comment }) =>
      apiClient.post(`/api/v2/residents/${id}/apartments/${uaId}/reject`, { comment })
        .then(r => r.data),
    { successKey: 'residents.toast.bindingRejected', errorKey: 'residents.toast.bindingRejectFailed', residentId: id },
  )
}

export function useUpdateBinding(id: number) {
  return useResidentMutation<{ uaId: number; is_owner?: boolean; is_primary?: boolean }>(
    ({ uaId, ...body }) =>
      apiClient.patch(`/api/v2/residents/${id}/apartments/${uaId}`, body).then(r => r.data),
    { successKey: 'residents.toast.bindingUpdated', errorKey: 'residents.toast.bindingUpdateFailed', residentId: id },
  )
}

export function useRemoveBinding(id: number) {
  return useResidentMutation<number>(
    uaId => apiClient.delete(`/api/v2/residents/${id}/apartments/${uaId}`).then(r => r.data),
    { successKey: 'residents.toast.bindingRemoved', errorKey: 'residents.toast.bindingRemoveFailed', residentId: id },
  )
}

export function useRequestDocuments(id: number) {
  return useResidentMutation<{ document_types: string[]; comment: string }>(
    body => apiClient.post(`/api/v2/residents/${id}/verification/request-documents`, body)
      .then(r => r.data),
    { successKey: 'residents.toast.documentsRequested', errorKey: 'residents.toast.documentsRequestFailed', residentId: id },
  )
}

export function useApproveVerification(id: number) {
  return useResidentMutation<{ notes?: string }>(
    body => apiClient.post(`/api/v2/residents/${id}/verification/approve`, body).then(r => r.data),
    { successKey: 'residents.toast.verified', errorKey: 'residents.toast.verifyFailed', residentId: id },
  )
}

export function useRejectVerification(id: number) {
  return useResidentMutation<{ notes: string }>(
    body => apiClient.post(`/api/v2/residents/${id}/verification/reject`, body).then(r => r.data),
    { successKey: 'residents.toast.verificationRejected', errorKey: 'residents.toast.verificationRejectFailed', residentId: id },
  )
}

/** Ускоритель поверх polling'а, а НЕ замена ему.
 *
 *  Канал `apartments:updates` несёт только события привязок
 *  (`apartment_request.*`). Статусы аккаунта и верификации событий не имеют
 *  вообще, а бот-путь верификации меняет привязки без публикации — поэтому
 *  30-секундный `refetchInterval` в useResidents/useResident остаётся
 *  основным механизмом свежести. WS лишь сокращает задержку там, где событие
 *  всё-таки есть: коллега подтвердил заявку — карточка обновилась сразу, а не
 *  через полминуты.
 */
export function useResidentsWebSocket() {
  const queryClient = useQueryClient()
  const onEvent = useCallback((event: { type: string; data: unknown }) => {
    if (typeof event.type !== 'string' || !event.type.startsWith('apartment_request.')) return
    for (const key of [
      ['residents'], ['resident'], ['residents-stats'],
      ['moderation'], ['address-stats'],
      ['apartment-detail'], ['apartments'], ['all-apartments'],
    ]) {
      queryClient.invalidateQueries({ queryKey: key })
    }
  }, [queryClient])
  useWebSocket('apartments', onEvent)
}
