import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '../utils/errorMessage'
import type { NewsItem, NewsItemStatus, NewsWatchConfig } from '../types/newsWatch'

/**
 * Мониторинг отключений (/api/v2/news-watch, manager): конфиг (источники,
 * описание комплекса, ключевые слова, auto_publish) и очередь новостей с
 * решениями publish/reject/retry-broadcast. DARK за VITE_NEWS_WATCH_ENABLED
 * (согласованно с backend NEWS_WATCH_ENABLED → 404).
 */
export const NEWS_WATCH_BASE = '/api/v2/news-watch'

export const newsWatchKeys = {
  config: ['news-watch-config'] as const,
  items: (status: NewsItemStatus) => ['news-watch-items', status] as const,
}

export function useNewsWatchConfig() {
  return useQuery<NewsWatchConfig>({
    queryKey: newsWatchKeys.config,
    queryFn: () => apiClient.get(`${NEWS_WATCH_BASE}/config`).then((r) => r.data),
  })
}

export function useSaveNewsWatchConfig() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: NewsWatchConfig) =>
      apiClient.put(`${NEWS_WATCH_BASE}/config`, payload).then((r) => r.data as NewsWatchConfig),
    onSuccess: (data) => {
      queryClient.setQueryData(newsWatchKeys.config, data)
      toast.success(t('newsWatch.toast.configSaved'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}

export function useNewsItems(status: NewsItemStatus) {
  return useQuery<{ items: NewsItem[]; total: number }>({
    queryKey: newsWatchKeys.items(status),
    queryFn: () => apiClient.get(`${NEWS_WATCH_BASE}/items`, { params: { status } }).then((r) => r.data),
    refetchInterval: 30_000,
  })
}

type Decision = 'publish' | 'reject' | 'retry-broadcast'

export function useNewsDecision() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: Decision }) =>
      apiClient.post(`${NEWS_WATCH_BASE}/items/${id}/${decision}`).then((r) => r.data as NewsItem),
    onSuccess: (_data, { decision }) => {
      queryClient.invalidateQueries({ queryKey: ['news-watch-items'] })
      toast.success(t(`newsWatch.toast.${decision === 'retry-broadcast' ? 'retried' : decision}`))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}
