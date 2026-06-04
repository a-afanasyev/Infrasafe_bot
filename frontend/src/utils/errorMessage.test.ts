import { describe, expect, it } from 'vitest'

import { safeErrorMessage } from './errorMessage'

const FALLBACK = 'Something went wrong'

function axiosError(detail: unknown) {
  // Minimal shape axios.isAxiosError accepts (checks isAxiosError === true).
  return { isAxiosError: true, response: { data: { detail } } } as unknown
}

describe('safeErrorMessage', () => {
  it('returns the API detail for a short string', () => {
    expect(safeErrorMessage(axiosError('Квартира недоступна'), FALLBACK)).toBe('Квартира недоступна')
  })

  it('falls back when detail is >= 200 chars (no leaking a huge payload)', () => {
    expect(safeErrorMessage(axiosError('x'.repeat(200)), FALLBACK)).toBe(FALLBACK)
  })

  it('falls back when detail is not a string', () => {
    expect(safeErrorMessage(axiosError({ nested: true }), FALLBACK)).toBe(FALLBACK)
  })

  it('falls back for an axios error without a detail field', () => {
    expect(safeErrorMessage({ isAxiosError: true, response: { data: {} } } as unknown, FALLBACK)).toBe(FALLBACK)
  })

  it('falls back for a non-axios error', () => {
    expect(safeErrorMessage(new Error('boom'), FALLBACK)).toBe(FALLBACK)
    expect(safeErrorMessage('plain string', FALLBACK)).toBe(FALLBACK)
    expect(safeErrorMessage(null, FALLBACK)).toBe(FALLBACK)
  })
})
