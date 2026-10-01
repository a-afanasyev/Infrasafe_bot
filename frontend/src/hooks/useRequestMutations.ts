import { useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '@/utils/errorMessage'
import { tSpecialization } from '../i18n/apiMaps'
import { KANBAN_QUERY_PREFIX } from './useKanban'
import { requestCommentsQueryKey, requestQueryKey } from './useRequestDetail'

/** Ответ PATCH /requests/{n}/category — см. api/requests/schemas.CategoryChangeOut. */
export interface CategoryChangeOut {
  no_op: boolean
  new_category: string
  new_specialization?: string | null
  redispatched: boolean
  /** assigned | grouped | disabled | failed | no_spec; null — передиспетч не требовался */
  dispatch_kind?: string | null
  executor_id?: number | null
  executor_name?: string | null
  executor_spec_mismatch: boolean
  can_reassign: boolean
}

/**
 * Итог смены категории для баннера карточки. `mismatch`: исполнитель «В работе»
 * остался, но его специализация не покрывает новую категорию. `unassigned`:
 * канон снял старую группу, а диспетч новую не поставил (выключен/упал) —
 * заявка «Новая» без группы, пул дежурных её не видит.
 */
export interface CategoryWarning {
  kind: 'mismatch' | 'unassigned'
  canReassign: boolean
}

const UNASSIGNED_DISPATCH_KINDS = new Set(['disabled', 'failed', 'no_spec'])

export function categoryChangeWarning(data: CategoryChangeOut): CategoryWarning | null {
  if (data.no_op) return null
  if (data.executor_spec_mismatch) return { kind: 'mismatch', canReassign: data.can_reassign }
  if (UNASSIGNED_DISPATCH_KINDS.has(data.dispatch_kind ?? '')) {
    return { kind: 'unassigned', canReassign: data.can_reassign }
  }
  return null
}

/** PATCH карточки заявки — общий транспорт канбана, карточки и смены исполнителя. */
export function patchRequest<T = unknown>(requestNumber: string, body: object): Promise<T> {
  return apiClient.patch(`/api/v2/requests/${requestNumber}`, body).then(r => r.data as T)
}

/** Канбан (все фильтры) + сама карточка — то, что меняет любой PATCH заявки. */
export function invalidateRequestViews(queryClient: QueryClient, requestNumber: string | null) {
  queryClient.invalidateQueries({ queryKey: requestQueryKey(requestNumber) })
  queryClient.invalidateQueries({ queryKey: KANBAN_QUERY_PREFIX })
}

const FALLBACK_ERROR = 'An error occurred'

export interface RequestMutationHandlers {
  /** Успешный PATCH карточки (статус/критичность/подтверждение/возврат). */
  onUpdated?: () => void
  /** Ответ смены категории (в т.ч. no_op) — для баннера несоответствия. */
  onCategoryChanged?: (data: CategoryChangeOut) => void
  onForceAccepted?: () => void
  onCommentPosted?: () => void
}

/**
 * Мутации карточки заявки дашборда (A9-P3-21: вынесены из RequestDetailModal).
 *
 * Тосты и инвалидации живут здесь, состояние формы — у вызывающего через
 * `handlers`. Ключи берутся из `useRequestDetail`, так что сброс кэша
 * совпадает с тем, что карточка реально читает.
 */
export function useRequestMutations(requestNumber: string | null, handlers: RequestMutationHandlers = {}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const updateRequest = useMutation({
    mutationFn: (data: Record<string, unknown>) => patchRequest(requestNumber as string, data),
    onSuccess: () => {
      toast.success(t('toast.requestUpdated'))
      invalidateRequestViews(queryClient, requestNumber)
      handlers.onUpdated?.()
    },
    onError: (error: unknown) => {
      toast.error(t('toast.requestUpdateFailed'), { description: safeErrorMessage(error, FALLBACK_ERROR) })
    },
  })

  // Смена категории — свой эндпоинт (канон MANAGER_CHANGE_CATEGORY): ответ
  // несёт итог передиспетча и флаг несоответствия специализации исполнителя,
  // которых голая карточка из PATCH не даёт.
  const changeCategory = useMutation({
    mutationFn: (category: string) =>
      apiClient.patch(`/api/v2/requests/${requestNumber}/category`, { category })
        .then(r => r.data as CategoryChangeOut),
    onSuccess: (data) => {
      if (data.no_op) {
        toast.info(t('kanban.categoryUnchanged'))
        handlers.onCategoryChanged?.(data)
        return
      }
      toast.success(t('toast.categoryUpdated'))
      if (data.redispatched && data.executor_name) {
        toast.info(t('kanban.categoryRedispatchedExecutor', { name: data.executor_name }))
      } else if (data.redispatched) {
        toast.info(t('kanban.categoryRedispatchedGroup', {
          spec: tSpecialization(data.new_specialization ?? '', t),
        }))
      }
      handlers.onCategoryChanged?.(data)
      invalidateRequestViews(queryClient, requestNumber)
      queryClient.invalidateQueries({ queryKey: requestCommentsQueryKey(requestNumber) })
    },
    onError: (error: unknown) => {
      toast.error(t('toast.categoryUpdateFailed'), { description: safeErrorMessage(error, FALLBACK_ERROR) })
    },
  })

  const forceAccept = useMutation({
    mutationFn: (note: string) =>
      patchRequest(requestNumber as string, { status: 'Принято', manager_confirmation_notes: note }),
    onSuccess: () => {
      toast.success(t('toast.requestForceAccepted'))
      invalidateRequestViews(queryClient, requestNumber)
      handlers.onForceAccepted?.()
    },
    onError: (error: unknown) => {
      toast.error(t('toast.requestForceAcceptFailed'), { description: safeErrorMessage(error, FALLBACK_ERROR) })
    },
  })

  const remindApplicant = useMutation({
    mutationFn: () => apiClient.post(`/api/v2/requests/${requestNumber}/remind-applicant`),
    onSuccess: () => {
      toast.success(t('toast.reminderSent'))
    },
    onError: (error: unknown) => {
      // 409 «житель заблокировал бота» — причину показываем, а не общий отказ.
      toast.error(t('toast.reminderFailed'), { description: safeErrorMessage(error, '') || undefined })
    },
  })

  const postComment = useMutation({
    mutationFn: (text: string) =>
      apiClient.post(`/api/v2/requests/${requestNumber}/comments`, { text, is_internal: true }).then(r => r.data),
    onSuccess: () => {
      toast.success(t('toast.noteAdded'))
      queryClient.invalidateQueries({ queryKey: requestCommentsQueryKey(requestNumber) })
      handlers.onCommentPosted?.()
    },
    onError: (error: unknown) => {
      toast.error(t('toast.noteAddFailed'), { description: safeErrorMessage(error, FALLBACK_ERROR) })
    },
  })

  return { updateRequest, changeCategory, forceAccept, remindApplicant, postComment }
}

export type ExecutorAssignment = number | 'duty'

/**
 * Назначение/смена исполнителя заявки (карточка «Сменить исполнителя» и
 * «Сотрудники → Назначить заявку»). `duty` — «дежурному»: спец резолвит сервер
 * по категории. Инвалидирует канбан, карточку и сотрудников (их счётчики заявок).
 */
export function useAssignRequestExecutor(options: {
  onSuccess?: () => void
  onError?: (error: unknown) => void
} = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ requestNumber, executor }: { requestNumber: string; executor: ExecutorAssignment }) =>
      patchRequest(
        requestNumber,
        executor === 'duty' ? { status: 'В работе', assign_to_duty: true } : { executor_id: executor },
      ),
    onSuccess: (_data, { requestNumber }) => {
      invalidateRequestViews(queryClient, requestNumber)
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      options.onSuccess?.()
    },
    onError: (error: unknown) => options.onError?.(error),
  })
}
