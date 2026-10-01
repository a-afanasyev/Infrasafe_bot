import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'

/**
 * Карточка заявки и её комментарии — единственное место, где собираются их
 * ключи кэша (A9-P3-21). Мутации заявки (`useRequestMutations`, смена
 * исполнителя, подсказка «Лифт работает?») инвалидируют ровно эти ключи, поэтому
 * собирать их руками в компонентах нельзя: расхождение ключа = карточка, которая
 * не обновляется после действия (класс AUD8 all-apartments).
 */
export const REQUEST_QUERY_PREFIX = ['request'] as const

export function requestQueryKey(requestNumber: string | null) {
  return [...REQUEST_QUERY_PREFIX, requestNumber] as const
}

export function requestCommentsQueryKey(requestNumber: string | null) {
  return ['comments', requestNumber] as const
}

export interface RequestComment {
  id: number
  comment_text: string
  is_internal: boolean
  created_at: string
}

export function useRequest(requestNumber: string | null) {
  // Ответ карточки широкий (InfraSafe-контекст, лифт, причины возврата) и
  // не типизирован — компонент читает поля по месту, как и до выноса.
  return useQuery({
    queryKey: requestQueryKey(requestNumber),
    queryFn: () => apiClient.get(`/api/v2/requests/${requestNumber}`).then(r => r.data),
    enabled: !!requestNumber,
  })
}

export function useRequestComments(requestNumber: string | null) {
  return useQuery<RequestComment[]>({
    queryKey: requestCommentsQueryKey(requestNumber),
    queryFn: () => apiClient.get(`/api/v2/requests/${requestNumber}/comments`).then(r => r.data),
    enabled: !!requestNumber,
  })
}
