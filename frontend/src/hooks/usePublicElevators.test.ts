import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor } from '@testing-library/react'
import { renderHook } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { usePublicElevators } from './usePublicElevators'

describe('usePublicElevators', () => {
  it('запрашивает /api/v2/public/elevators с ?lang и отдаёт ответ как есть', async () => {
    const langs: string[] = []
    server.use(
      http.get('*/api/v2/public/elevators', ({ request }) => {
        langs.push(new URL(request.url).searchParams.get('lang') ?? '')
        return HttpResponse.json({ yards: [], dispatch_phone: '+998 71 123-45-67', generated_at: '2026-09-06T10:00:00Z' })
      }),
    )
    const { result } = renderHook(() => usePublicElevators('uz'))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(langs).toEqual(['uz'])
    expect(result.current.data?.dispatch_phone).toBe('+998 71 123-45-67')
    expect(result.current.data?.yards).toEqual([])
  })
})
