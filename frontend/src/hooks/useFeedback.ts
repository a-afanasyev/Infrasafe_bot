import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import i18n from '../i18n'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '@/utils/errorMessage'

export type FeedbackType = 'complaint' | 'wish'
export type FeedbackStatus = 'new' | 'in_review' | 'resolved'

export interface FeedbackListItem {
  id: number
  type: FeedbackType
  status: FeedbackStatus
  text: string
  has_media: boolean
  author_name?: string | null
  created_at?: string | null
}

export interface FeedbackListResponse {
  items: FeedbackListItem[]
  total: number
}

export interface FeedbackDetail {
  id: number
  type: FeedbackType
  status: FeedbackStatus
  text: string
  source: string
  media_ids: number[]
  reply?: string | null
  replied_at?: string | null
  author_name?: string | null
  author_phone?: string | null
  created_at?: string | null
}

export interface FeedbackFilters {
  type?: FeedbackType
  status?: FeedbackStatus
}

export function useFeedbackList(filters: FeedbackFilters = {}) {
  return useQuery<FeedbackListResponse>({
    queryKey: ['feedback', filters],
    queryFn: () =>
      apiClient
        .get('/api/v2/feedback', { params: { ...filters, limit: 100, offset: 0 } })
        .then((r) => r.data),
    staleTime: 30_000,
  })
}

export function useFeedbackDetail(id: number | null) {
  return useQuery<FeedbackDetail>({
    queryKey: ['feedback', id],
    queryFn: () => apiClient.get(`/api/v2/feedback/${id}`).then((r) => r.data),
    enabled: id != null,
    staleTime: 30_000,
  })
}

export function useUpdateFeedback(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { status?: FeedbackStatus; reply?: string }) =>
      apiClient.patch(`/api/v2/feedback/${id}`, body).then((r) => r.data),
    onSuccess: (_data, body) => {
      toast.success(i18n.t(body.reply ? 'feedback.replySent' : 'feedback.statusChanged'))
      queryClient.invalidateQueries({ queryKey: ['feedback'] })
    },
    onError: (error: unknown, body) => {
      toast.error(i18n.t(body.reply ? 'feedback.replyFailed' : 'feedback.statusChangeFailed'), {
        description: safeErrorMessage(error, 'Error'),
      })
    },
  })
}
