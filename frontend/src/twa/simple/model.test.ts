import { describe, it, expect } from 'vitest'
import { testI18n } from '../../test/test-utils'
import type { TwaRequest } from '../types'
import { firstLine, isUrgent, poolAddress, returnReason, sortMine, tileState, urgencyStripClass } from './model'

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
    ]
    const order = sortMine(tasks, new Set(['pending'])).map((t) => t.request_number)
    expect(order).toEqual(['returned', 'legacy-urgent', 'new-urgent', 'old-normal', 'newer-normal', 'pending'])
    // Вход не мутируется.
    expect(tasks[0].request_number).toBe('old-normal')
  })

  it('tileState и причина возврата', () => {
    expect(tileState(task('a', { status: 'Возвращена' }), new Set())).toBe('returned')
    expect(tileState(task('a', { status: 'Закуп' }), new Set())).toBe('inWork')
    expect(tileState(task('a', { status: 'Возвращена' }), new Set(['a']))).toBe('pending')
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
