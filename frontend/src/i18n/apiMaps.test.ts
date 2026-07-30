import { afterEach, describe, expect, it, vi } from 'vitest'
import type { TFunction } from 'i18next'

import { tCategory, tSpecialization, tStatus, tUrgency } from './apiMaps'

// Identity-ish t: echoes the resolved i18n key so we can assert the mapping.
const t = ((key: string) => `T:${key}`) as unknown as TFunction

afterEach(() => vi.restoreAllMocks())

describe('apiMaps known values → i18n keys', () => {
  it('maps every category surface (RU + EN keys)', () => {
    expect(tStatus('В работе', t)).toBe('T:status.in_progress')
    expect(tStatus('Возвращена', t)).toBe('T:status.returned') // PR7: канон-статус возврата
    expect(tUrgency('Критическая', t)).toBe('T:urgency.critical')
    expect(tCategory('Электрика', t)).toBe('T:category.electrical')
    expect(tCategory('plumbing', t)).toBe('T:category.plumbing') // EN key from bot
    expect(tSpecialization('electrician', t)).toBe('T:specialization.electrician')
  })

  it('tUrgency dual-read: canonical keys AND legacy russian map to same i18n key (TASK 17)', () => {
    // канон-ключи
    expect(tUrgency('low', t)).toBe('T:urgency.normal')
    expect(tUrgency('medium', t)).toBe('T:urgency.medium')
    expect(tUrgency('high', t)).toBe('T:urgency.urgent')
    expect(tUrgency('critical', t)).toBe('T:urgency.critical')
    // legacy-рус (cached-клиенты / смешанные данные)
    expect(tUrgency('Обычная', t)).toBe('T:urgency.normal')
    expect(tUrgency('Срочная', t)).toBe('T:urgency.urgent')
  })
})

describe('apiMaps unknown values → raw + console.warn', () => {
  it('warns and echoes the raw value for each mapper', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(tStatus('???', t)).toBe('???')
    expect(tUrgency('???', t)).toBe('???')
    expect(tCategory('???', t)).toBe('???')
    expect(tSpecialization('???', t)).toBe('???')
    expect(warn).toHaveBeenCalledTimes(4)
  })
})
