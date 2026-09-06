import { describe, expect, it } from 'vitest'
import { formatBusinessDate, formatInstant, formatMoney } from './format'

// Дата состояния и дата платежа приходят как YYYY-MM-DD без времени: календарный
// день не должен зависеть от зоны браузера, иначе снимок «уезжает» на сутки.
describe('formatBusinessDate', () => {
  it('печатает тот же календарный день, а не предыдущий', () => {
    // Локаль в тестах не зафиксирована (дашборд печатает дату в языке интерфейса),
    // поэтому проверяем сам инвариант: день остаётся первым, а не 31 августа.
    const formatted = formatBusinessDate('2026-09-01')
    expect(formatted).toMatch(/(^|\D)0?1(\D|$)/)
    expect(formatted).not.toMatch(/31/)
  })

  it('пустое значение — прочерк, а не «Invalid Date»', () => {
    expect(formatBusinessDate(null)).toBe('—')
    expect(formatBusinessDate(undefined)).toBe('—')
    expect(formatInstant(null)).toBe('—')
  })
})

describe('formatMoney', () => {
  it('берёт валюту из данных сервиса и не выдумывает её', () => {
    expect(formatMoney('120.50', 'UZS')).toBe('120.50 UZS')
    expect(formatMoney('120.50')).toBe('120.50')
    expect(formatMoney(null)).toBe('—')
  })
})
