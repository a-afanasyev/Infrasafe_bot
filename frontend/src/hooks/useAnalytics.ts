import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { downloadCsv, downloadPost } from '../utils/download'
import type { RequestCard } from './useKanban'
import type { DateRange } from '../utils/analyticsPeriod'
import type {
  AddressStatsOut,
  AnalyticsPeriod,
  BacklogOut,
  ChannelStatsOut,
  CostStatsOut,
  ExecutorStatsRow,
  QualityStatsOut,
  ReportRequestsOut,
  ReportScope,
  RequestStatsOut,
  ShiftStatsOut,
  StatsGranularity,
} from '../types/api'

// Canonical useShiftStats lives HERE (FE-02): useShifts.ts re-exports it.
// Keep a single hook per queryKey — a second implementation with different
// options silently shares/clobbers the same cache entry.

export type { AnalyticsPeriod, RequestStatsOut, ShiftStatsOut }

const STATS = '/api/v2/requests/stats'
const STALE_MS = 30_000

export function useShiftStats(period: AnalyticsPeriod = '7d') {
  return useQuery<ShiftStatsOut>({
    queryKey: ['shift-stats', period],
    queryFn: () =>
      apiClient.get('/api/v2/shifts/stats', { params: { period } }).then(r => r.data),
    staleTime: STALE_MS,
    placeholderData: keepPreviousData,
  })
}

function periodParams(range: DateRange) {
  return { date_from: range.from, date_to: range.to }
}

function useStats<T>(path: string, range: DateRange | null, extra: Record<string, unknown> = {}) {
  return useQuery<T>({
    queryKey: ['request-stats', path, range?.from, range?.to, extra],
    queryFn: () =>
      apiClient.get(`${STATS}${path}`, { params: { ...periodParams(range!), ...extra } }).then(r => r.data),
    enabled: range !== null,
    staleTime: STALE_MS,
    placeholderData: keepPreviousData,
  })
}

/** `range` null — период невалиден, запросов нет. */
export function useRequestStats(range: DateRange | null, granularity: StatsGranularity | null) {
  return useStats<RequestStatsOut>('', range, granularity ? { granularity } : {})
}

export function useExecutorStats(range: DateRange | null) {
  return useStats<ExecutorStatsRow[]>('/executors', range)
}

export function useQualityStats(range: DateRange | null) {
  return useStats<QualityStatsOut>('/quality', range)
}

export function useAddressStats(range: DateRange | null) {
  return useStats<AddressStatsOut>('/addresses', range)
}

export function useChannelStats(range: DateRange | null, granularity: StatsGranularity | null) {
  return useStats<ChannelStatsOut>('/channels', range, granularity ? { granularity } : {})
}

export function useCostStats(range: DateRange | null) {
  return useStats<CostStatsOut>('/costs', range)
}

export function useBacklog(enabled = true) {
  return useQuery<BacklogOut>({
    queryKey: ['request-stats', '/backlog'],
    queryFn: () => apiClient.get(`${STATS}/backlog`).then(r => r.data),
    enabled,
    staleTime: STALE_MS,
  })
}

/** Принятые в периоде заявки исполнителя — раскрытая строка таблицы. */
export function useExecutorAcceptedRequests(executorId: number | null, range: DateRange) {
  return useQuery<RequestCard[]>({
    queryKey: ['executor-accepted', executorId, range.from, range.to],
    queryFn: () =>
      apiClient
        .get('/api/v2/requests', {
          params: {
            executor_id: executorId,
            status: 'Принято',
            accepted_from: range.from,
            accepted_to: range.to,
            limit: 200,
          },
        })
        .then(r => r.data),
    enabled: executorId !== null,
    staleTime: STALE_MS,
  })
}

export function exportCompletedCsv(range: DateRange, executorId?: number) {
  const suffix = executorId != null ? `_executor${executorId}` : ''
  return downloadCsv(
    `${STATS}/export`,
    { ...periodParams(range), ...(executorId != null ? { executor_id: executorId } : {}) },
    `completed_requests_${range.from}_${range.to}${suffix}.csv`,
  )
}

export function exportExecutorsCsv(range: DateRange) {
  return downloadCsv(
    `${STATS}/export/executors`,
    periodParams(range),
    `executors_summary_${range.from}_${range.to}.csv`,
  )
}

export type ReportSheet = 'summary' | 'dynamics' | 'buildings' | 'register'
export const REPORT_SHEETS: readonly ReportSheet[] = ['summary', 'dynamics', 'buildings', 'register']

export interface OfficialReportOptions {
  lang: 'ru' | 'uz'
  organization: string
  signer: string
  sheets: ReportSheet[]
  /** PNG в base64 (без `data:`-префикса) или null — без логотипа. */
  logo: string | null
}

/** Отчёт для проверяющих органов (.xlsx): отмеченные листы, шапка с логотипом. */
export function exportOfficialReport(range: DateRange, opts: OfficialReportOptions) {
  return downloadPost(
    `${STATS}/report`,
    periodParams(range),
    opts,
    `official_report_${range.from}_${range.to}_${opts.lang}.xlsx`,
  )
}

/** Таблица вкладки «Отчёт»: все поступившие или только принятые в периоде. */
export function useReportRequests(range: DateRange | null, scope: ReportScope) {
  return useStats<ReportRequestsOut>('/report/requests', range, { scope })
}
