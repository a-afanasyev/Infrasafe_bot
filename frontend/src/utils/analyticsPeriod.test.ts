import { describe, expect, it } from 'vitest'
import {
  autoGranularity,
  daysInRange,
  formatBucket,
  formatRange,
  isValidRange,
  pctChange,
  presetRange,
} from './analyticsPeriod'

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

describe('presetRange', () => {
  const today = '2026-10-12'
  it.each([
    ['today', '2026-10-12', '2026-10-12'],
    ['last7', '2026-10-06', '2026-10-12'],
    ['thisMonth', '2026-10-01', '2026-10-12'],
    ['lastMonth', '2026-09-01', '2026-09-30'],
    ['thisYear', '2026-01-01', '2026-10-12'],
    ['lastYear', '2025-01-01', '2025-12-31'],
  ] as const)('%s', (preset, from, to) => {
    expect(presetRange(preset, today)).toEqual({ from, to })
  })

  it('прошлый месяц через границу года и в коротком феврале', () => {
    expect(presetRange('lastMonth', '2026-01-15')).toEqual({ from: '2025-12-01', to: '2025-12-31' })
    expect(presetRange('lastMonth', '2028-03-01')).toEqual({ from: '2028-02-01', to: '2028-02-29' })
  })
})

describe('autoGranularity', () => {
  it('пороги совпадают с бэкендом', () => {
    expect(autoGranularity({ from: '2026-01-01', to: '2026-03-03' })).toBe('day') // 62 дня
    expect(autoGranularity({ from: '2026-01-01', to: '2026-03-04' })).toBe('month')
    expect(autoGranularity({ from: '2025-01-01', to: '2026-12-31' })).toBe('month')
    expect(autoGranularity({ from: '2024-01-01', to: '2026-12-31' })).toBe('year')
  })
})

describe('isValidRange', () => {
  it('порядок, формат и длина', () => {
    expect(isValidRange({ from: '2026-10-01', to: '2026-10-31' })).toBe(true)
    expect(isValidRange({ from: '2026-10-31', to: '2026-10-01' })).toBe(false)
    expect(isValidRange({ from: '', to: '2026-10-01' })).toBe(false)
    expect(isValidRange({ from: '2019-01-01', to: '2026-10-01' })).toBe(false)
    expect(daysInRange({ from: '2026-10-01', to: '2026-10-31' })).toBe(31)
  })
})

describe('подписи', () => {
  it('бакеты оси по срезу', () => {
    expect(formatBucket('2026-10-02', 'day', MONTHS)).toBe('02.10')
    expect(formatBucket('2026-10', 'month', MONTHS)).toBe('окт 2026')
    expect(formatBucket('2026', 'year', MONTHS)).toBe('2026')
  })

  it('период и изменение', () => {
    expect(formatRange({ from: '2026-10-01', to: '2026-10-31' })).toBe('01.10.2026 — 31.10.2026')
    expect(formatRange({ from: '2026-10-12', to: '2026-10-12' })).toBe('12.10.2026')
    expect(pctChange(12, 10)).toBe(20)
    expect(pctChange(5, 0)).toBeNull()
    expect(pctChange(null, 3)).toBeNull()
  })
})
