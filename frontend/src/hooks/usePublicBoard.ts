import { useQuery } from '@tanstack/react-query'
import { publicClient } from '../api/publicClient'

// Anonymized request row — no number, no description, no personal data.
export interface PublicBoardRequest {
  category: string
  status: string
  created_at: string
}

export interface PublicBoardData {
  status_counts: Record<string, number>
  active_requests: PublicBoardRequest[]
  active_executors: number
  avg_resolution_hours: number | null
  // Среднее арифметическое оценок жителей при приёмке (1–5), null — оценок нет.
  avg_rating: number | null
  // Страница жителей. Опциональны: ответ бэкенда до появления полей.
  // completed_month — Выполнена/Исполнено/Принято в текущем бизнес-месяце.
  completed_month?: number
  // Счётчики по категориям: new / in_progress / completed_month.
  category_counts?: Partial<Record<RequestGroup, Record<string, number>>>
}

export type RequestGroup = 'new' | 'in_progress' | 'completed_month'

// Public board data via polling — no WebSocket, no auth.
export function usePublicBoard() {
  return useQuery<PublicBoardData>({
    queryKey: ['public-board'],
    queryFn: () => publicClient.get('/api/v2/public/board').then((r) => r.data),
    refetchInterval: 45_000,
    staleTime: 30_000,
  })
}
