import { describe, expect, it } from 'vitest'
import type { Notice } from '../../hooks/useNotices'
import { bodyOf, draftError, emptyDraft, eventsByDay, isScheduled, monthGrid } from './noticeModel'

// Зона показа в тестах — Asia/Tashkent (UTC+5), см. utils/timezone.

function notice(over: Partial<Notice>): Notice {
  return {
    id: 1, kind: 'news', resource: null, source: 'manual', title_ru: 'Новость', title_uz: '', text_ru: '', text_uz: '',
    place_ru: '', place_uz: '', icon: '', important: false, status: 'published', state: 'active',
    publish_at: '2026-11-13T05:00:00Z', starts_at: null, ends_at: null, all_day: false, expires_at: null,
    created_at: '2026-11-13T05:00:00Z', ...over,
  }
}

describe('noticeModel — тело запроса', () => {
  it('новость: окно и место не уходят, пустые даты — null', () => {
    const body = bodyOf({ ...emptyDraft('news'), title: { ru: ' Собрание ', uz: '' }, place: { ru: 'x', uz: '' } })
    expect(body).toMatchObject({
      kind: 'news', resource: null, title_ru: 'Собрание', place_ru: '',
      publish_at: null, starts_at: null, ends_at: null, expires_at: null,
    })
  })

  it('отключение: стенное время объекта → UTC; без срока показа уходит с витрины по окончании', () => {
    const draft = { ...emptyDraft('outage', '2026-11-18'), title: { ru: 'Свет', uz: '' }, resource: 'power' as const }
    const body = bodyOf(draft)
    expect(body.starts_at).toBe('2026-11-18T05:00:00.000Z') // 10:00 Ташкент
    expect(body.ends_at).toBe('2026-11-18T09:00:00.000Z')
    expect(body.expires_at).toBe(body.ends_at)
    expect(body.resource).toBe('power')
  })

  it('проверка формы и «запланировано»', () => {
    expect(draftError(emptyDraft('news'))).toBe('title')
    const outage = { ...emptyDraft('outage'), title: { ru: 'x', uz: '' } }
    expect(draftError(outage)).toBe('window')
    expect(draftError({ ...outage, startsAt: '2026-11-18T14:00', endsAt: '2026-11-18T10:00' })).toBe('order')
    expect(draftError({ ...outage, startsAt: '2026-11-18T10:00', endsAt: '2026-11-18T14:00' })).toBeNull()

    const now = new Date('2026-11-14T00:00:00Z')
    expect(isScheduled({ ...emptyDraft('news'), publishAt: '2026-11-16T09:00' }, now)).toBe(true)
    expect(isScheduled({ ...emptyDraft('news'), publishAt: '2026-11-13T09:00' }, now)).toBe(false)
    expect(isScheduled(emptyDraft('news'), now)).toBe(false)
  })
})

describe('noticeModel — календарь', () => {
  it('новость — в день публикации; отключение — на каждый день окна; отложенная публикация — пунктиром', () => {
    const map = eventsByDay([
      notice({ id: 1 }),
      notice({ id: 2, kind: 'outage', resource: 'heating', starts_at: '2026-11-23T04:00:00Z', ends_at: '2026-11-24T08:00:00Z' }),
      notice({ id: 3, kind: 'outage', resource: 'power', state: 'scheduled', publish_at: '2026-11-16T04:00:00Z',
               starts_at: '2026-11-18T05:00:00Z', ends_at: '2026-11-18T09:00:00Z' }),
      notice({ id: 4, source: 'staff', kind: 'outage', starts_at: '2026-11-14T10:40:00Z', ends_at: null }),
    ])
    expect(map.get('2026-11-13')?.map((e) => [e.notice.id, e.tone])).toEqual([[1, 'news']])
    expect(map.get('2026-11-23')?.[0].tone).toBe('outage')
    expect(map.get('2026-11-24')?.map((e) => e.notice.id)).toEqual([2])
    expect(map.get('2026-11-16')?.map((e) => [e.notice.id, e.tone])).toEqual([[3, 'pending']])
    expect(map.get('2026-11-18')?.map((e) => e.notice.id)).toEqual([3])
    expect(map.get('2026-11-14')?.[0].tone).toBe('staff')
  })

  it('сетка месяца начинается с понедельника и кратна неделе', () => {
    const days = monthGrid(2026, 10) // ноябрь 2026: 1-е — воскресенье
    expect(days[0]).toBe('2026-10-26')
    expect(days.length % 7).toBe(0)
    expect(days).toContain('2026-11-30')
    expect(days[days.length - 1]).toBe('2026-12-06')
  })
})
