import { describe, it, expect } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { createTwaQueryClient, shouldRetryQuery } from './queryRetry'

const httpError = (status: number) => ({ response: { status } })

describe('TWA: повторы запросов', () => {
  it('сетевая ошибка и 5xx — до двух повторов', () => {
    const network = new Error('Network Error')
    expect(shouldRetryQuery(0, network)).toBe(true)
    expect(shouldRetryQuery(1, network)).toBe(true)
    expect(shouldRetryQuery(2, network)).toBe(false)
    expect(shouldRetryQuery(0, httpError(502))).toBe(true)
    expect(shouldRetryQuery(2, httpError(502))).toBe(false)
  })

  it('4xx не повторяем, кроме 408/429', () => {
    for (const s of [400, 401, 403, 404, 409, 422]) {
      expect(shouldRetryQuery(0, httpError(s))).toBe(false)
    }
    expect(shouldRetryQuery(0, httpError(408))).toBe(true)
    expect(shouldRetryQuery(0, httpError(429))).toBe(true)
  })

  it('клиент TWA: queries — по правилу выше, мутации — без авторетрая', () => {
    const qc = createTwaQueryClient()
    expect(qc).toBeInstanceOf(QueryClient)
    const defaults = qc.getDefaultOptions()
    expect(defaults.queries?.retry).toBe(shouldRetryQuery)
    expect(defaults.mutations?.retry).toBe(false)
  })
})
