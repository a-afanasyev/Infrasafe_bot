import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'

import { server } from '../test/msw/server'
import { apiClient } from './client'

// 429 от edge-nginx (лимит на IP) повторяется самим клиентом с паузой по
// Retry-After — пользователь видит короткую загрузку, а не «Ошибка».

describe('apiClient: повтор на 429', () => {
  it('после 429 с Retry-After повторяет запрос и отдаёт успешный ответ', async () => {
    let calls = 0
    server.use(
      http.get('*/api/v2/work-reports', () => {
        calls += 1
        return calls === 1
          ? new HttpResponse(null, { status: 429, headers: { 'Retry-After': '0' } })
          : HttpResponse.json({ items: [], total: 0 })
      }),
    )

    const res = await apiClient.get('/api/v2/work-reports')

    expect(res.status).toBe(200)
    expect(calls).toBe(2)
  })

  it('после исчерпания повторов отдаёт 429 наружу', async () => {
    let calls = 0
    server.use(
      http.get('*/api/v2/work-reports', () => {
        calls += 1
        return new HttpResponse(null, { status: 429, headers: { 'Retry-After': '0' } })
      }),
    )

    await expect(apiClient.get('/api/v2/work-reports')).rejects.toMatchObject({
      response: { status: 429 },
    })
    expect(calls).toBe(3) // исходный + 2 повтора
  })
})
