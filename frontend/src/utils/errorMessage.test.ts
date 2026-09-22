import { describe, expect, it } from 'vitest'

import { apiErrorCode, apiErrorDetail, apiErrorStatus, safeErrorMessage } from './errorMessage'
import { getErrorMessage } from '../twa/utils/errors'

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

// A9-P3-20: единый канон разбора detail (дашборд + TWA).
describe('apiErrorDetail / apiErrorCode — единый канон', () => {
  it('422-массив → «поле: причина; …» строкой (не объект в JSX)', () => {
    const err = axiosError([
      { loc: ['body', 'email'], msg: 'value is not a valid email' },
      { loc: ['body', 'password'], msg: 'too short' },
    ])
    expect(apiErrorDetail(err)).toBe('email: value is not a valid email; password: too short')
    expect(safeErrorMessage(err, FALLBACK)).toBe('email: value is not a valid email; password: too short')
  })

  it('{code, message} → message; код отдельно', () => {
    const err = axiosError({ code: 'phone_taken', message: 'Телефон занят' })
    expect(apiErrorDetail(err)).toBe('Телефон занят')
    expect(apiErrorCode(err)).toBe('phone_taken')
  })

  it('код из заголовка X-Error-Code (detail при этом строка)', () => {
    const err = { isAxiosError: true, response: { headers: { 'x-error-code': 'contact_required' }, data: { detail: 'Сначала поделитесь контактом' } } }
    expect(apiErrorCode(err)).toBe('contact_required')
    expect(apiErrorDetail(err)).toBe('Сначала поделитесь контактом')
  })

  it('строковый detail кода не имеет', () => {
    expect(apiErrorCode(axiosError('x'))).toBeNull()
    expect(apiErrorCode(null)).toBeNull()
  })

  it('пустые/битые detail → null', () => {
    expect(apiErrorDetail(axiosError('  '))).toBeNull()
    expect(apiErrorDetail(axiosError([{ foo: 1 }]))).toBeNull()
    expect(apiErrorDetail(new Error('x'))).toBeNull()
  })

  it('apiErrorStatus читает статус ответа', () => {
    expect(apiErrorStatus({ response: { status: 409 } })).toBe(409)
    expect(apiErrorStatus(new Error('x'))).toBeNull()
  })

  it('TWA getErrorMessage делегирует в канон, затем message, затем fallback', () => {
    expect(getErrorMessage(axiosError([{ loc: ['body', 'a'], msg: 'bad' }]))).toBe('a: bad')
    expect(getErrorMessage({ message: 'Network Error' })).toBe('Network Error')
    expect(getErrorMessage(null, 'fb')).toBe('fb')
  })
})
