import { describe, it, expect } from 'vitest'
import { testI18n } from '../../test/test-utils'
import { buildStatusReason, LISTED_MAX } from './statusReason'
import { MAX_REASON_LEN } from '../../types/elevators'

// Причина смены статуса лифта из подсказки: бэкенд режет reason по
// MAX_REASON_LEN (500) с 422 — длину гарантируем на клиенте.
const t = testI18n.getFixedT('ru')

describe('buildStatusReason', () => {
  it('одна заявка — «подтверждение заявки N»', () => {
    expect(buildStatusReason(t, ['260905-001'])).toBe('подтверждение заявки 260905-001')
  })

  it('до LISTED_MAX номеров — все перечислены без «+N»', () => {
    const numbers = ['a', 'b', 'c', 'd', 'e'].slice(0, LISTED_MAX)
    expect(buildStatusReason(t, numbers)).toBe(`подтверждение ${LISTED_MAX} заявок: a, b, c, d, e`)
  })

  it('больше LISTED_MAX — первые LISTED_MAX и «+N»', () => {
    expect(buildStatusReason(t, ['1', '2', '3', '4', '5', '6', '7'])).toBe('подтверждение 7 заявок: 1, 2, 3, 4, 5 +2')
  })

  it('жёсткий срез до MAX_REASON_LEN с «…» при аномально длинных номерах', () => {
    const numbers = Array.from({ length: 3 }, () => 'x'.repeat(300))
    const reason = buildStatusReason(t, numbers)
    expect(reason.length).toBe(MAX_REASON_LEN)
    expect(reason.endsWith('…')).toBe(true)
  })
})
