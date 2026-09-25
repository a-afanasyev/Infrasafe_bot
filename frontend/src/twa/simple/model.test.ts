import { describe, it, expect } from 'vitest'
import { testI18n } from '../../test/test-utils'
import type { TwaRequest } from '../types'
import { NO_MARKS, firstLine, isUrgent, poolAddress, returnReason, sortMine, tileState, urgencyStripClass, type QueueMarks } from './model'

const marks = (pending: string[] = [], retake: string[] = []): QueueMarks => ({ pending: new Set(pending), retake: new Set(retake) })

const task = (n: string, over: Partial<TwaRequest> = {}): TwaRequest => ({
  request_number: n,
  status: 'В работе',
  category: 'plumbing',
  created_at: '2026-09-20T10:00:00Z',
  ...over,
})

describe('sortMine: вернули → срочные → по времени, «ждёт отправки» — в конце', () => {
  it('порядок', () => {
    const tasks = [
      task('old-normal', { created_at: '2026-09-01T10:00:00Z' }),
      task('new-urgent', { urgency: 'high', created_at: '2026-09-25T10:00:00Z' }),
      task('pending', { urgency: 'critical', created_at: '2026-08-01T10:00:00Z' }),
      task('returned', { status: 'Возвращена', created_at: '2026-09-26T10:00:00Z' }),
      task('newer-normal', { created_at: '2026-09-10T10:00:00Z' }),
      task('legacy-urgent', { urgency: 'Критическая', created_at: '2026-09-24T10:00:00Z' }),
      task('purchase', { status: 'Закуп', urgency: 'critical', created_at: '2026-07-01T10:00:00Z' }),
      task('retake', { created_at: '2026-09-26T11:00:00Z' }),
    ]
    const order = sortMine(tasks, marks(['pending'], ['retake'])).map((t) => t.request_number)
    expect(order).toEqual(['returned', 'retake', 'legacy-urgent', 'new-urgent', 'old-normal', 'newer-normal', 'purchase', 'pending'])
    // Вход не мутируется.
    expect(tasks[0].request_number).toBe('old-normal')
  })

  it('tileState и причина возврата', () => {
    expect(tileState(task('a', { status: 'Возвращена' }), NO_MARKS)).toBe('returned')
    expect(tileState(task('a'), NO_MARKS)).toBe('inWork')
    // Закуп / Уточнение / Новая — не оранжевое «В работе», а «Ждёт менеджера».
    for (const status of ['Закуп', 'Уточнение', 'Новая']) {
      expect(tileState(task('a', { status }), NO_MARKS)).toBe('waiting')
    }
    expect(tileState(task('a', { status: 'Возвращена' }), marks(['a']))).toBe('pending')
    expect(tileState(task('a'), marks([], ['a']))).toBe('retake')
    expect(returnReason({ return_reason: '  ', manager_return_reason: 'Грязно' })).toBe('Грязно')
    expect(returnReason({ return_reason: null })).toBeNull()
  })
})

describe('срочность', () => {
  it('urgent = high/critical (ключ и legacy-рус); полоса по уровню', () => {
    expect(isUrgent('high')).toBe(true)
    expect(isUrgent('medium')).toBe(false)
    expect(isUrgent(null)).toBe(false)
    expect(urgencyStripClass('critical')).toBe('bg-red-600')
    expect(urgencyStripClass('Срочная')).toBe('bg-orange-500')
    expect(urgencyStripClass('low')).toBeNull()
  })
})

describe('poolAddress / firstLine', () => {
  const t = testI18n.getFixedT('ru')

  it('структурный адрес: дом · подъезд · кв', () => {
    expect(
      poolAddress(
        { request_number: '1', status: 'Новая', category: 'x', building_address: 'Дом 5', entrance: 2, apartment_number: '45', address: 'полный' },
        t,
      ),
    ).toBe('Дом 5 · Подъезд 2 · кв 45')
  })

  it('без привязки к квартире — строка адреса с сервера', () => {
    expect(poolAddress({ request_number: '1', status: 'Новая', category: 'x', address: 'Двор, у 3 подъезда' }, t)).toBe(
      'Двор, у 3 подъезда',
    )
  })

  it('firstLine — первая непустая строка', () => {
    expect(firstLine('\n  Течёт кран  \nи ещё')).toBe('Течёт кран')
    expect(firstLine(undefined)).toBe('')
  })
})
