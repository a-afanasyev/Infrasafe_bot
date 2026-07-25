import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor } from '@testing-library/react'
import { renderHook } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { usePublicWorkReports, publicWorkReportMediaUrl } from './usePublicWorkReports'
import type { PublicWorkReport } from '../types/workReports'

const TOTAL = 15
const PAGE_SIZE = 12

function makeItems(count: number, startId: number): PublicWorkReport[] {
  return Array.from({ length: count }, (_, i) => ({
    id: startId + i,
    category_key: 'plumbing',
    address: 'дом 1',
    completed_on: '2026-07-01',
    before: [1],
    after: [2],
  }))
}

function installFeedHandler() {
  server.use(
    http.get('*/api/v2/public/work-reports', ({ request }) => {
      const url = new URL(request.url)
      const offset = Number(url.searchParams.get('offset') ?? '0')
      const limit = Number(url.searchParams.get('limit') ?? String(PAGE_SIZE))
      const remaining = Math.max(TOTAL - offset, 0)
      const count = Math.min(limit, remaining)
      return HttpResponse.json({
        items: makeItems(count, offset + 1),
        total: TOTAL,
        limit,
        offset,
      })
    }),
  )
}

describe('usePublicWorkReports', () => {
  it('первая страница запрашивается с offset=0 и limit=12', async () => {
    installFeedHandler()
    const { result } = renderHook(() => usePublicWorkReports())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.pages).toHaveLength(1)
    const firstPage = result.current.data?.pages[0]
    expect(firstPage?.offset).toBe(0)
    expect(firstPage?.limit).toBe(PAGE_SIZE)
    expect(firstPage?.items).toHaveLength(PAGE_SIZE)
    expect(result.current.hasNextPage).toBe(true)
  })

  it('«Показать ещё» запрашивает offset = сумма уже загруженных айтемов и склеивает страницы', async () => {
    installFeedHandler()
    const { result } = renderHook(() => usePublicWorkReports())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.pages[0].items).toHaveLength(PAGE_SIZE)

    await result.current.fetchNextPage()
    await waitFor(() => expect(result.current.isFetchingNextPage).toBe(false))

    expect(result.current.data?.pages).toHaveLength(2)
    const secondPage = result.current.data?.pages[1]
    // offset должен быть суммой items, загруженных до этого момента (12), а
    // не жёстко захардкоженным PAGE_SIZE второй раз подряд — тест ловит
    // именно накопительную логику loaded/allPages.
    expect(secondPage?.offset).toBe(PAGE_SIZE)
    expect(secondPage?.items).toHaveLength(TOTAL - PAGE_SIZE)

    // Склейка: суммарно все загруженные айтемы = все страницы вместе.
    const allIds = result.current.data?.pages.flatMap((p) => p.items.map((i) => i.id))
    expect(allIds).toHaveLength(TOTAL)
    expect(new Set(allIds).size).toBe(TOTAL)
  })

  it('getNextPageParam возвращает undefined и hasNextPage=false, когда все total загружены', async () => {
    installFeedHandler()
    const { result } = renderHook(() => usePublicWorkReports())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.pages[0].items).toHaveLength(PAGE_SIZE)

    await result.current.fetchNextPage()
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2))
    await waitFor(() => expect(result.current.hasNextPage).toBe(false))
  })
})

describe('publicWorkReportMediaUrl', () => {
  it('строит прямой URL байтов фото по report_id/media_id', () => {
    const url = publicWorkReportMediaUrl(42, 7)
    expect(url).toContain('/api/v2/public/work-reports/42/media/7')
  })
})
