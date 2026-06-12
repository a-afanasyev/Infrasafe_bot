import { describe, expect, it } from 'vitest'
import { isValidTelegramAuth } from './telegramAuth'

// FE-04: window.onTelegramAuth получает внешний неконтролируемый payload —
// до POST'а обязательны id (число) и hash (непустая строка).

describe('isValidTelegramAuth', () => {
  it('принимает валидный payload виджета', () => {
    expect(isValidTelegramAuth({
      id: 48617336,
      hash: 'abc123def456',
      auth_date: 1760000000,
      first_name: 'Ivan',
      username: 'ivan',
    })).toBe(true)
  })

  it('принимает минимальный payload (только id + hash)', () => {
    expect(isValidTelegramAuth({ id: 1, hash: 'h' })).toBe(true)
  })

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['строка', 'not-an-object'],
    ['число', 42],
    ['пустой объект', {}],
    ['без hash', { id: 1 }],
    ['без id', { hash: 'abc' }],
    ['id строкой', { id: '1', hash: 'abc' }],
    ['hash не строка', { id: 1, hash: 123 }],
    ['пустой hash', { id: 1, hash: '' }],
    ['id NaN', { id: NaN, hash: 'abc' }],
    ['id Infinity', { id: Infinity, hash: 'abc' }],
  ])('отклоняет невалидный payload: %s', (_label, payload) => {
    expect(isValidTelegramAuth(payload)).toBe(false)
  })
})
