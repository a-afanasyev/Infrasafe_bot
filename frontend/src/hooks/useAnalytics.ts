import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'

// Note: ShiftStatsOut and useShiftStats are also exported from useShifts.ts.
// Here we re-export the type alias and provide a typed wrapper using AnalyticsPeriod.

export type AnalyticsPeriod = '7d' | '30d' | '90d'

export interface DayStats {
  date: string
  created: number
  closed: number
}

export interface ExecutorStat {
  user_id: number
  name: string
  completed: number
  avg_hours: number | null
  score: number
}

export interface ActivityItem {
  event_type: string  // 'created' | 'assigned' | 'completed' | 'cancelled'
  request_number: string
  executor_name: string | null
  created_at: string  // ISO string
}

export interface RequestStatsOut {
  by_day: DayStats[]
  by_category: Record<string, number>
  by_status: Record<string, number>
  top_executors: ExecutorStat[]
  recent_actions: ActivityItem[]
  total_requests: number
  avg_resolution_hours: number | null
  avg_satisfaction: number | null
}

export interface ShiftStatsOut {
  active_shifts: number
  active_executors: number
  coverage_pct: number
  avg_efficiency: number | null
  shifts_today: number
  pending_transfers: number
}

export function useShiftStats(period: AnalyticsPeriod = '7d') {
  return useQuery<ShiftStatsOut>({
    queryKey: ['shift-stats', period],
    queryFn: () =>
      apiClient.get('/api/v2/shifts/stats', { params: { period } }).then(r => r.data),
    staleTime: 30_000,
  })
}

export function useRequestStats(period: AnalyticsPeriod) {
  return useQuery<RequestStatsOut>({
    queryKey: ['request-stats', period],
    queryFn: () =>
      apiClient.get('/api/v2/requests/stats', { params: { period } }).then(r => r.data),
    staleTime: 30_000,
  })
}
