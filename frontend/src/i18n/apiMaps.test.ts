import { afterEach, describe, expect, it, vi } from 'vitest'
import type { TFunction } from 'i18next'

import {
  tAnalyticsEvent,
  tAnalyticsStatus,
  tApprovalStatus,
  tCategory,
  tPriority,
  tRole,
  tShiftType,
  tSpecialization,
  tStatus,
  tUrgency,
} from './apiMaps'

// Identity-ish t: echoes the resolved i18n key so we can assert the mapping.
const t = ((key: string) => `T:${key}`) as unknown as TFunction

afterEach(() => vi.restoreAllMocks())

describe('apiMaps known values → i18n keys', () => {
  it('maps every category surface (RU + EN keys)', () => {
    expect(tStatus('В работе', t)).toBe('T:status.in_progress')
    expect(tUrgency('Критическая', t)).toBe('T:urgency.critical')
    expect(tCategory('Электрика', t)).toBe('T:category.electrical')
    expect(tCategory('plumbing', t)).toBe('T:category.plumbing') // EN key from bot
    expect(tSpecialization('electrician', t)).toBe('T:specialization.electrician')
    expect(tShiftType('emergency', t)).toBe('T:shiftType.emergency')
    expect(tAnalyticsStatus('in_progress', t)).toBe('T:analyticsStatus.in_progress')
    expect(tAnalyticsEvent('completed', t)).toBe('T:analyticsEvent.completed')
    expect(tRole('manager', t)).toBe('T:role.manager')
    expect(tPriority(3, t)).toBe('T:priority.3')
    expect(tPriority('5', t)).toBe('T:priority.5')
    expect(tApprovalStatus('approved', t)).toBe('T:approvalStatus.approved')
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
    expect(tShiftType('???', t)).toBe('???')
    expect(tAnalyticsStatus('???', t)).toBe('???')
    expect(tAnalyticsEvent('???', t)).toBe('???')
    expect(tRole('???', t)).toBe('???')
    expect(tPriority(99, t)).toBe('99')
    expect(tApprovalStatus('???', t)).toBe('???')
    expect(warn).toHaveBeenCalledTimes(10)
  })
})
