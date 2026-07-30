import { describe, expect, it } from 'vitest'

import { pruneSubmittedDrafts } from './drafts'

describe('pruneSubmittedDrafts (AUD6-P2-10)', () => {
  it('удаляет черновики, ушедшие в запрос и не менявшиеся', () => {
    const next = pruneSubmittedDrafts(
      { m1: { value: '10', comment: '' } },
      [{ meter_id: 'm1', value: '10', comment: null }],
    )
    expect(next).toEqual({})
  })

  it('сохраняет правку, введённую пока запрос летел', () => {
    // Отправили value=10, но к моменту ответа контролёр уже ввёл 12.
    const next = pruneSubmittedDrafts(
      { m1: { value: '12', comment: '' } },
      [{ meter_id: 'm1', value: '10', comment: null }],
    )
    expect(next).toEqual({ m1: { value: '12', comment: '' } })
  })

  it('не трогает черновики, не входившие в запрос', () => {
    const next = pruneSubmittedDrafts(
      {
        m1: { value: '10', comment: '' },
        m2: { value: '20', comment: 'введено позже' },
      },
      [{ meter_id: 'm1', value: '10', comment: null }],
    )
    expect(next).toEqual({ m2: { value: '20', comment: 'введено позже' } })
  })

  it('учитывает изменение только комментария', () => {
    const next = pruneSubmittedDrafts(
      { m1: { value: '10', comment: 'новый комментарий' } },
      [{ meter_id: 'm1', value: '10', comment: null }],
    )
    expect(next.m1).toBeDefined()
  })
})
