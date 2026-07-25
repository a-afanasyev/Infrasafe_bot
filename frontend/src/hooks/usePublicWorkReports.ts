import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
// publicClient здесь — из api/publicClient.ts (withCredentials: false, для
// анонимных эндпоинтов), НЕ одноимённый экспорт из api/client.ts
// (withCredentials: true, для login/OTP) — см. naming-trap комментарий в
// обоих файлах.
import { publicClient, BASE_URL } from '../api/publicClient'
import type { PublicWorkReport, PublicWorkReportsPage } from '../types/workReports'

// Публичная лента визуальных отчётов «до/после» (GET /api/v2/public/work-reports,
// T8). Первый в кодовой базе infinite-scroll-хук («Показать ещё» на будущей
// странице архива, T12) — прецедента для копирования нет, поэтому используем
// React Query v5 useInfiniteQuery напрямую (initialPageParam обязателен;
// getNextPageParam возвращает undefined, когда страниц больше нет — v5-конвенция,
// НЕ v4-булев hasNextPage).

const BASE = '/api/v2/public/work-reports'
// 24 = максимум, который может выставить менеджер в WorkReportsCfg.limit
// (`ge=1, le=24` на бэкенде). Размер страницы обязан покрывать его целиком:
// WorkReportsModule нарезает карточки из pages[0], и при PAGE_SIZE < limit
// табло молча показывало бы меньше, чем настроено. Ключ запроса общий с
// страницей архива — она переиспользует те же загруженные страницы.
const PAGE_SIZE = 24

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

// Один отчёт по id — под страницу отчёта /uk/work-reports/{id}. Отдельный
// запрос, а не поиск в уже загруженной ленте: страница открывается по прямой
// ссылке, и отчёт может быть вне первой страницы (или вообще за пределами
// `limit`, который настраивает менеджер).
export function usePublicWorkReport(reportId: number | undefined) {
  return useQuery<PublicWorkReport>({
    queryKey: ['public-work-report', reportId],
    queryFn: () => publicClient.get(`${BASE}/${reportId}`).then((r) => r.data),
    enabled: reportId !== undefined && Number.isFinite(reportId),
    staleTime: 30_000,
    // Отчёт могли снять с публикации — 404 это нормальный ответ, а не сбой
    // сети; повторять запрос смысла нет.
    retry: false,
  })
}

// Прямой URL байтов фото для <img src> — НИКОГДА не через axios/JSON и не
// через blob: (CSP на этом деплое блокирует blob: на /uk/*, см. reference
// про CSP-landmine).
export function publicWorkReportMediaUrl(reportId: number, mediaId: number): string {
  return `${BASE_URL}${BASE}/${reportId}/media/${mediaId}`
}
