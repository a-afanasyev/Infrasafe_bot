import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '../utils/errorMessage'

/**
 * «Новости и уведомления» (/api/v2/board-config/notices, действие notices.manage): лента
 * новостей и плановых отключений. Жители видят эти записи на табло, главной и
 * в TWA прежними списками витрины — сервер собирает их из той же таблицы.
 */
// Под префиксом витрины — он уже пропускается edge обеих площадок.
export const NOTICES_BASE = '/api/v2/board-config/notices'

export type NoticeKind = 'news' | 'outage'
export type NoticeState = 'draft' | 'scheduled' | 'active' | 'expired' | 'closed'
export const NOTICE_RESOURCES = ['water', 'heating', 'power', 'gas', 'internet', 'other'] as const
export type NoticeResource = (typeof NOTICE_RESOURCES)[number]

export interface Notice {
  id: number
  kind: NoticeKind
  resource: NoticeResource | null
  source: 'manual' | 'news_watch' | 'staff'
  title_ru: string
  title_uz: string
  text_ru: string
  text_uz: string
  place_ru: string
  place_uz: string
  icon: string
  important: boolean
  status: 'draft' | 'published' | 'closed'
  state: NoticeState
  publish_at: string | null
  starts_at: string | null
  ends_at: string | null
  all_day: boolean
  expires_at: string | null
  created_at: string | null
}

/** Тело создания/правки: служебные поля сервер не принимает. */
export interface NoticeBody {
  kind: NoticeKind
  resource: NoticeResource | null
  title_ru: string
  title_uz: string
  text_ru: string
  text_uz: string
  place_ru: string
  place_uz: string
  icon: string
  important: boolean
  publish_at: string | null
  starts_at: string | null
  ends_at: string | null
  all_day: boolean
  expires_at: string | null
}

interface NoticesPage { items: Notice[]; total: number }

const KEY = 'notices'

export function useNotices(params: { kind?: NoticeKind; status?: string; from?: string; to?: string } = {}) {
  return useQuery<NoticesPage>({
    queryKey: [KEY, params],
    queryFn: () => apiClient.get(NOTICES_BASE, { params: { ...params, limit: 500 } }).then((r) => r.data),
    refetchInterval: 60_000,
  })
}

type Action =
  | { type: 'create'; body: NoticeBody; publish: boolean }
  | { type: 'update'; id: number; body: NoticeBody; publish: boolean }
  | { type: 'publish' | 'close' | 'delete'; id: number }

async function run(action: Action): Promise<void> {
  if (action.type === 'create') {
    // null на создании = «не задано»: сервер принимает только заданные поля.
    const body = Object.fromEntries(Object.entries(action.body).filter(([, v]) => v !== null))
    await apiClient.post(NOTICES_BASE, { ...body, publish: action.publish })
  } else if (action.type === 'update') {
    await apiClient.patch(`${NOTICES_BASE}/${action.id}`, action.body)
    if (action.publish) await apiClient.post(`${NOTICES_BASE}/${action.id}/publish`)
  } else if (action.type === 'delete') {
    await apiClient.delete(`${NOTICES_BASE}/${action.id}`)
  } else {
    await apiClient.post(`${NOTICES_BASE}/${action.id}/${action.type}`)
  }
}

export function useNoticeAction() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [KEY] })
      // Витрина (табло, превью редактора) читает те же записи.
      queryClient.invalidateQueries({ queryKey: ['board-config'] })
      toast.success(t('notices.toast.saved'))
    },
    onError: (err) => toast.error(safeErrorMessage(err, t('common.error'))),
  })
}
