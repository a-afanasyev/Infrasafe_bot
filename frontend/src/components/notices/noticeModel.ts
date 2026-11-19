/** Модель формы и календаря раздела «Новости и уведомления». Без React и сети. */
import type { Notice, NoticeBody, NoticeKind, NoticeResource, NoticeScope } from '../../hooks/useNotices'
import { datetimeLocalToIso, fromDisplayTz, isoToDatetimeLocal, toDisplayTz } from '../../utils/timezone'

/** Поля формы: даты — строки `datetime-local` в зоне объекта. */
export interface NoticeDraft {
  kind: NoticeKind
  resource: NoticeResource
  title: { ru: string; uz: string }
  text: { ru: string; uz: string }
  place: { ru: string; uz: string }
  important: boolean
  /** Значок записи: формой не правится, но при сохранении не теряется. */
  icon: string
  publishAt: string
  startsAt: string
  endsAt: string
  allDay: boolean
  expiresAt: string
  scope: NoticeScope
  scopeIds: number[]
  /** Разослать в Telegram. У уже разосланной записи галочка только показывает факт. */
  broadcast: boolean
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
    icon: '',
    publishAt: kind === 'news' && day ? `${day}T09:00` : '',
    startsAt: kind === 'outage' && day ? `${day}T10:00` : '',
    endsAt: kind === 'outage' && day ? `${day}T14:00` : '',
    allDay: false,
    expiresAt: '',
    scope: 'all',
    scopeIds: [],
    broadcast: false,
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
    icon: n.icon,
    publishAt: local(n.publish_at),
    startsAt: local(n.starts_at),
    endsAt: local(n.ends_at),
    allDay: n.all_day,
    expiresAt: local(n.expires_at),
    scope: n.scope,
    scopeIds: [...n.scope_ids],
    broadcast: n.broadcast_status !== 'none',
  }
}

/** Чего не хватает для сохранения: ключ перевода `notices.form.error.*` или null. */
export function draftError(d: NoticeDraft): 'title' | 'window' | 'order' | 'scope' | null {
  if (!d.title.ru.trim()) return 'title'
  if (d.scope !== 'all' && d.scopeIds.length === 0) return 'scope'
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
    icon: d.icon,
    important: d.important,
    publish_at: datetimeLocalToIso(d.publishAt) ?? null,
    starts_at: outage ? datetimeLocalToIso(d.startsAt) ?? null : null,
    ends_at: endsAt,
    all_day: outage && d.allDay,
    // Пусто = «до конца отключения» (считает сервер): продлили окно — продлился показ.
    expires_at: datetimeLocalToIso(d.expiresAt) ?? null,
    scope: d.scope,
    scope_ids: d.scope === 'all' ? [] : d.scopeIds,
    broadcast: d.broadcast,
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

/** Границы сетки для запроса: начало первого и конец последнего дня в зоне объекта. */
export function gridWindow(days: string[]): { from: string; to: string } {
  return { from: fromDisplayTz(`${days[0]}T00:00`), to: fromDisplayTz(`${days[days.length - 1]}T23:59`) }
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

/** Отключение идёт сейчас: опубликовано, началось и не закрыто (срок мог уже выйти). */
export function ongoingOutages(items: Notice[], now: number): Notice[] {
  return items.filter((n) => n.kind === 'outage' && n.state === 'active' && (!n.starts_at || Date.parse(n.starts_at) <= now))
}
