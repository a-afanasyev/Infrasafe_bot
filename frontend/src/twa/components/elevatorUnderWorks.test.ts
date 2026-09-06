import { describe, it, expect } from 'vitest'
import { formatStatusSince, parseUnderWorksError, telHref } from './elevatorUnderWorks'
import { isElevatorUnderWorks } from '../../types/elevators'

// Р18: контракт 409 из `api/elevators/errors.py` + канон статусов «идут работы».

describe('parseUnderWorksError', () => {
  const detail = {
    code: 'elevator_under_works',
    status: 'under_repair',
    status_since: '2026-09-01T07:30:00Z',
    label: 'ул. Ленина 1, подъезд 2, лифт 1',
  }

  it('разбирает 409 с машинным кодом', () => {
    expect(parseUnderWorksError({ response: { status: 409, data: { detail } } })).toEqual({
      status: 'under_repair',
      statusSince: '2026-09-01T07:30:00Z',
      label: 'ул. Ленина 1, подъезд 2, лифт 1',
    })
  })

  it('409 другого происхождения (строковый detail) — не наш', () => {
    expect(parseUnderWorksError({ response: { status: 409, data: { detail: 'conflict' } } })).toBeNull()
  })

  it('422 с тем же телом — не наш (код проверяется вместе со статусом)', () => {
    expect(parseUnderWorksError({ response: { status: 422, data: { detail } } })).toBeNull()
  })

  it('произвольная ошибка / отсутствие ответа — null', () => {
    expect(parseUnderWorksError(new Error('network'))).toBeNull()
    expect(parseUnderWorksError(null)).toBeNull()
  })

  it('status_since = null допустим', () => {
    const body = { response: { status: 409, data: { detail: { ...detail, status_since: null } } } }
    expect(parseUnderWorksError(body)?.statusSince).toBeNull()
  })
})

describe('formatStatusSince', () => {
  it('пустой / битый момент → null (текст рендерится без «с …»)', () => {
    expect(formatStatusSince(null)).toBeNull()
    expect(formatStatusSince(undefined)).toBeNull()
    expect(formatStatusSince('не дата')).toBeNull()
  })

  it('ISO → человеческая строка', () => {
    expect(formatStatusSince('2026-09-01T07:30:00Z')).toContain('2026')
  })
})

describe('telHref', () => {
  it('оставляет только цифры и «+» (как в публичном виджете)', () => {
    expect(telHref('+998 71 200-00-00')).toBe('tel:+998712000000')
    expect(telHref('тел. 1234')).toBe('tel:1234')
  })
})

describe('isElevatorUnderWorks', () => {
  it('в работах — только ремонт и ТО', () => {
    expect(isElevatorUnderWorks('under_repair')).toBe(true)
    expect(isElevatorUnderWorks('maintenance')).toBe(true)
    expect(isElevatorUnderWorks('working')).toBe(false)
    expect(isElevatorUnderWorks('not_working')).toBe(false)
    expect(isElevatorUnderWorks(null)).toBe(false)
    expect(isElevatorUnderWorks(undefined)).toBe(false)
  })
})
