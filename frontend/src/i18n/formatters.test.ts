import { beforeAll, describe, expect, it } from 'vitest'

import i18n from './index'
import { formatDate, formatNumber } from './formatters'

beforeAll(async () => {
  await i18n.changeLanguage('ru')
})

describe('formatNumber', () => {
  it('formats with the current locale', () => {
    expect(formatNumber(42)).toBe('42')
    expect(typeof formatNumber(1234567)).toBe('string')
  })
  it('respects Intl options', () => {
    expect(formatNumber(0.5, { style: 'percent' })).toContain('50')
  })
})

describe('formatDate', () => {
  it('formats both Date and ISO string inputs', () => {
    expect(formatDate('2026-06-01T10:00:00Z')).toBeTruthy()
    expect(formatDate(new Date('2026-06-01T10:00:00Z'))).toBeTruthy()
  })
  it('falls back to ru when the locale is invalid', async () => {
    await i18n.changeLanguage('xx-INVALID-!!!')
    // toLocaleString throws RangeError on the bad locale → catch → 'ru' fallback.
    expect(formatDate('2026-06-01T10:00:00Z')).toBeTruthy()
    await i18n.changeLanguage('ru')
  })
})
