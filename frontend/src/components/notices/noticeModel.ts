/** Модель формы и календаря раздела «Новости и уведомления». Без React и сети. */
import type { Notice, NoticeBody, NoticeKind, NoticeResource } from '../../hooks/useNotices'
import { datetimeLocalToIso, isoToDatetimeLocal, toDisplayTz } from '../../utils/timezone'

/** Поля формы: даты — строки `datetime-local` в зоне объекта. */
export interface NoticeDraft {
  kind: NoticeKind
  resource: NoticeResource
  title: { ru: string; uz: string }
  text: { ru: string; uz: string }
  place: { ru: string; uz: string }
  important: boolean
  publishAt: string
  startsAt: string
  endsAt: string
  allDay: boolean
  expiresAt: string
}

const local = (iso: string | null): string => (iso ? isoToDatetimeLocal(iso) : '')

/** Новая запись; `day` (YYYY-MM-DD) — день, выбранный в календаре. */
export function emptyDraft(kind: NoticeKind, day?: string): NoticeDraft {
  return {
    kind,
    resource: 'water',
    title: { ru: '', uz: '' },
    text: { ru: '', uz: '' },
    place: { ru: '', uz: '' },
    important: false,
    publishAt: kind === 'news' && day ? `${day}T09:00` : '',
    startsAt: kind === 'outage' && day ? `${day}T10:00` : '',
    endsAt: kind === 'outage' && day ? `${day}T14:00` : '',
    allDay: false,
    expiresAt: '',
  }
}

export function draftOf(n: Notice): NoticeDraft {
  return {
    kind: n.kind,
    resource: n.resource ?? 'other',
    title: { ru: n.title_ru, uz: n.title_uz },
    text: { ru: n.text_ru, uz: n.text_uz },
    place: { ru: n.place_ru, uz: n.place_uz },
    important: n.important,
    publishAt: local(n.publish_at),
    startsAt: local(n.starts_at),
    endsAt: local(n.ends_at),
    allDay: n.all_day,
    expiresAt: local(n.expires_at),
  }
}

/** Чего не хватает для сохранения: ключ перевода `notices.form.error.*` или null. */
export function draftError(d: NoticeDraft): 'title' | 'window' | 'order' | null {
  if (!d.title.ru.trim()) return 'title'
  if (d.kind === 'outage') {
    if (!d.startsAt || !d.endsAt) return 'window'
    if (d.endsAt < d.startsAt) return 'order'
  }
  return null
}

export function bodyOf(d: NoticeDraft): NoticeBody {
  const outage = d.kind === 'outage'
  const endsAt = outage ? datetimeLocalToIso(d.endsAt) ?? null : null
  return {
    kind: d.kind,
    resource: outage ? d.resource : null,
    title_ru: d.title.ru.trim(),
    title_uz: d.title.uz.trim(),
    text_ru: d.text.ru.trim(),
    text_uz: d.text.uz.trim(),
    place_ru: outage ? d.place.ru.trim() : '',
    place_uz: outage ? d.place.uz.trim() : '',
    icon: '',
    important: d.important,
    publish_at: datetimeLocalToIso(d.publishAt) ?? null,
    starts_at: outage ? datetimeLocalToIso(d.startsAt) ?? null : null,
    ends_at: endsAt,
    all_day: outage && d.allDay,
    // Отключение без своего срока показа уходит с витрины, когда закончится.
    expires_at: datetimeLocalToIso(d.expiresAt) ?? endsAt,
  }
}

/** Публикация в будущем — запись «запланирована», а не опубликована сейчас. */
export const isScheduled = (d: NoticeDraft, now = new Date()): boolean => {
  const iso = datetimeLocalToIso(d.publishAt)
  return iso !== undefined && new Date(iso).getTime() > now.getTime()
}

// ── календарь ─────────────────────────────────────────────────────────

export type CalendarTone = 'news' | 'outage' | 'staff' | 'channel' | 'pending'

export interface CalendarEvent {
  notice: Notice
  tone: CalendarTone
  /** Момент события на этом дне для подписи времени (ISO) или null. */
  at: string | null
}

const dayKey = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export const dayKeyOf = (iso: string): string => dayKey(toDisplayTz(iso))

function toneOf(n: Notice): CalendarTone {
  if (n.state === 'draft') return 'pending'
  if (n.source === 'news_watch') return 'channel'
  if (n.source === 'staff') return 'staff'
  return n.kind === 'outage' ? 'outage' : 'news'
}

const MAX_SPAN_DAYS = 62

/** События по дням (YYYY-MM-DD в зоне объекта): окно отключения — на каждый его
 *  день, новость — в день публикации, отложенная публикация — пунктирной меткой. */
export function eventsByDay(notices: Notice[]): Map<string, CalendarEvent[]> {
  const out = new Map<string, CalendarEvent[]>()
  const push = (key: string, ev: CalendarEvent) => out.set(key, [...(out.get(key) ?? []), ev])
  for (const n of notices) {
    const tone = toneOf(n)
    if (n.starts_at) {
      const cursor = toDisplayTz(n.starts_at)
      const last = dayKeyOf(n.ends_at ?? n.starts_at)
      for (let i = 0; i < MAX_SPAN_DAYS; i += 1) {
        const key = dayKey(cursor)
        push(key, { notice: n, tone, at: i === 0 ? n.starts_at : null })
        if (key >= last) break
        cursor.setDate(cursor.getDate() + 1)
      }
      if (n.state === 'scheduled' && n.publish_at && dayKeyOf(n.publish_at) < dayKeyOf(n.starts_at)) {
        push(dayKeyOf(n.publish_at), { notice: n, tone: 'pending', at: n.publish_at })
      }
    } else {
      const at = n.publish_at ?? n.created_at
      if (at) push(dayKeyOf(at), { notice: n, tone: n.state === 'scheduled' ? 'pending' : tone, at })
    }
  }
  return out
}

/** Сетка месяца с понедельника: 5–6 недель по 7 дней (YYYY-MM-DD). */
export function monthGrid(year: number, month: number): string[] {
  const first = new Date(year, month, 1)
  const start = new Date(year, month, 1 - ((first.getDay() + 6) % 7))
  const days: string[] = []
  const cursor = new Date(start)
  while (days.length < 42) {
    days.push(dayKey(cursor))
    cursor.setDate(cursor.getDate() + 1)
    if (days.length % 7 === 0 && (cursor.getMonth() !== month || cursor.getFullYear() !== year) && days.length >= 28) break
  }
  return days
}
