import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type {
  AnalyticsPeriod,
  DayStats,
  ExecutorStat,
  ActivityItem,
  RequestStatsOut,
  ShiftStatsOut,
} from '../types/api'

// Note: ShiftStatsOut and useShiftStats are also exported from useShifts.ts.
// Here we re-export the type alias and provide a typed wrapper using AnalyticsPeriod.

export type { AnalyticsPeriod, DayStats, ExecutorStat, ActivityItem, RequestStatsOut, ShiftStatsOut }

export function useShiftStats(period: AnalyticsPeriod = '7d') {
  return useQuery<ShiftStatsOut>({
    queryKey: ['shift-stats', period],
    queryFn: () =>
      apiClient.get('/api/v2/shifts/stats', { params: { period } }).then(r => r.data),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
}

export function useRequestStats(period: AnalyticsPeriod) {
  return useQuery<RequestStatsOut>({
    queryKey: ['request-stats', period],
    queryFn: () =>
      apiClient.get('/api/v2/requests/stats', { params: { period } }).then(r => r.data),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
}
