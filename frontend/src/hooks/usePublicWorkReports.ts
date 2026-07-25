import { useInfiniteQuery } from '@tanstack/react-query'
// publicClient здесь — из api/publicClient.ts (withCredentials: false, для
// анонимных эндпоинтов), НЕ одноимённый экспорт из api/client.ts
// (withCredentials: true, для login/OTP) — см. naming-trap комментарий в
// обоих файлах.
import { publicClient, BASE_URL } from '../api/publicClient'
import type { PublicWorkReportsPage } from '../types/workReports'

// Публичная лента визуальных отчётов «до/после» (GET /api/v2/public/work-reports,
// T8). Первый в кодовой базе infinite-scroll-хук («Показать ещё» на будущей
// странице архива, T12) — прецедента для копирования нет, поэтому используем
// React Query v5 useInfiniteQuery напрямую (initialPageParam обязателен;
// getNextPageParam возвращает undefined, когда страниц больше нет — v5-конвенция,
// НЕ v4-булев hasNextPage).

const BASE = '/api/v2/public/work-reports'
const PAGE_SIZE = 12

export function usePublicWorkReports() {
  return useInfiniteQuery<PublicWorkReportsPage>({
    queryKey: ['public-work-reports'],
    queryFn: ({ pageParam }) =>
      publicClient
        .get(BASE, { params: { limit: PAGE_SIZE, offset: pageParam } })
        .then((r) => r.data),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, page) => sum + page.items.length, 0)
      return loaded < lastPage.total ? loaded : undefined
    },
    staleTime: 30_000,
  })
}

// Прямой URL байтов фото для <img src> — НИКОГДА не через axios/JSON и не
// через blob: (CSP на этом деплое блокирует blob: на /uk/*, см. reference
// про CSP-landmine).
export function publicWorkReportMediaUrl(reportId: number, mediaId: number): string {
  return `${BASE_URL}${BASE}/${reportId}/media/${mediaId}`
}
