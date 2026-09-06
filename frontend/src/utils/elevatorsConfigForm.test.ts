import { describe, it, expect } from 'vitest'
import { configDraftFrom, configDraftToPayload } from './elevatorsConfigForm'
import type { ElevatorsConfigOut } from '../types/elevators'

// Р18a: тумблер «разрешить заявки жителей при ремонте и ТО» ходит в обе стороны.

const BASE: ElevatorsConfigOut = {
  module_public: false,
  allow_resident_requests_under_works: false,
  downtime_threshold_days: { not_working: 7, under_repair: null },
  resident_notifications: { repair_started: true, maintenance_started: true, back_in_service: true },
  staff_reminders: { maintenance: [30, 14, 7], certification: [30], contract: [30], overdue_weekly: true },
}

describe('elevatorsConfigForm — тумблер Р18a', () => {
  it('черновик читает значение из ответа', () => {
    expect(configDraftFrom(BASE).allow_resident_requests_under_works).toBe(false)
    expect(
      configDraftFrom({ ...BASE, allow_resident_requests_under_works: true })
        .allow_resident_requests_under_works,
    ).toBe(true)
  })

  it('старый ответ без поля читается как «запрет включён»', () => {
    const legacy = { ...BASE } as Partial<ElevatorsConfigOut>
    delete legacy.allow_resident_requests_under_works
    expect(
      configDraftFrom(legacy as ElevatorsConfigOut).allow_resident_requests_under_works,
    ).toBe(false)
  })

  it('payload несёт значение в PUT /config', () => {
    const draft = configDraftFrom({ ...BASE, allow_resident_requests_under_works: true })
    expect(configDraftToPayload(draft).allow_resident_requests_under_works).toBe(true)
  })
})
