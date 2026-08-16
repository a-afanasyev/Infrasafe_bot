// «Прочитано/непрочитано» для карточек канбана — хранится только в браузере
// (решение владельца: серверной модели нет). Следствие: на другом компьютере
// индикаторы начинают с чистого листа и первая загрузка подсветит карточки
// отслеживаемых колонок — это самолечится за один проход.
//
// Что считается «версией» карточки: `updated_at` заявки. Ответ жителя на
// уточнение пишется в notes и бампает эту колонку, а внутренний комментарий
// менеджера строку заявки не трогает. Точного сигнала «пришло новое от жителя»
// в схеме нет, поэтому версией служит время последнего изменения строки, а
// собственные действия менеджера гасятся штампом сразу после успеха.

/** Запись «что видел менеджер». Двух полей нельзя заменить одним числом:
 *  по версии нельзя вычислить возраст записи, а прунинг нужен по возрасту. */
export interface SeenEntry {
  /** Тот `updated_at`, который менеджер видел — с ним и сравниваем. */
  versionMs: number
  /** Когда отметили — по нему считается TTL. */
  seenAtMs: number
}

export type SeenMap = Record<string, SeenEntry>

export const SEEN_TTL_MS = 30 * 24 * 60 * 60 * 1000
export const SEEN_MAX_ENTRIES = 500

const KEY_PREFIX = 'uk_kanban_seen_v1'

export function storageKeyFor(userId: number): string {
  return `${KEY_PREFIX}:${userId}`
}

// Рабочая копия в памяти. Она же — источник стабильной ссылки для
// useSyncExternalStore: новый объект на каждый getSnapshot означал бы
// бесконечный ре-рендер. И она же обеспечивает деградацию при недоступном
// localStorage (приватный режим, исчерпанная квота): точки продолжают гаснуть
// до перезагрузки вкладки, вместо того чтобы фича молча выключилась.
let cache: SeenMap | null = null
let cacheUserId: number | null = null

const listeners = new Set<() => void>()

function notify(): void {
  listeners.forEach(fn => fn())
}

/** Подписка на изменения (текущая вкладка). Возвращает функцию отписки. */
export function subscribeSeen(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Сбросить кэш — реакция на запись в соседней вкладке (событие `storage`). */
export function invalidateSeenCache(): void {
  cache = null
  cacheUserId = null
  notify()
}

function isEntry(value: unknown): value is SeenEntry {
  if (typeof value !== 'object' || value === null) return false
  const entry = value as Partial<SeenEntry>
  return Number.isFinite(entry.versionMs) && Number.isFinite(entry.seenAtMs)
}

function loadFromStorage(userId: number): SeenMap {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(storageKeyFor(userId))
  } catch {
    return {}
  }
  if (!raw) return {}

  try {
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return {}
    // Отфильтровываем мусор поштучно: одна битая запись не должна стоить
    // менеджеру всей истории прочитанного.
    const clean: SeenMap = {}
    for (const [number, entry] of Object.entries(parsed as Record<string, unknown>)) {
      if (isEntry(entry)) clean[number] = entry
    }
    return clean
  } catch {
    return {}
  }
}

/** Текущая карта отметок. Ссылка стабильна, пока не было записи. */
export function readSeen(userId: number): SeenMap {
  if (cache === null || cacheUserId !== userId) {
    cache = loadFromStorage(userId)
    cacheUserId = userId
  }
  return cache
}

/** Прунинг: сначала по возрасту, затем по потолку (самые старые вылетают). */
function prune(map: SeenMap, nowMs: number): SeenMap {
  const alive = Object.entries(map).filter(([, e]) => nowMs - e.seenAtMs < SEEN_TTL_MS)
  if (alive.length <= SEEN_MAX_ENTRIES) return Object.fromEntries(alive)

  const newestFirst = [...alive].sort((a, b) => b[1].seenAtMs - a[1].seenAtMs)
  return Object.fromEntries(newestFirst.slice(0, SEEN_MAX_ENTRIES))
}

/** Отметить карточку прочитанной на версии `version` (ISO-строка). */
export function markSeen(userId: number, requestNumber: string, version: string | null): void {
  const versionMs = version === null ? NaN : Date.parse(version)
  if (!Number.isFinite(versionMs)) return

  const current = readSeen(userId)
  const existing = current[requestNumber]
  // Повтор со старой версией не откатывает отметку назад: иначе гонка между
  // WS-обновлением и штампом могла бы «разпрочитать» карточку.
  if (existing && existing.versionMs >= versionMs) return

  const nowMs = Date.now()
  const next = prune({ ...current, [requestNumber]: { versionMs, seenAtMs: nowMs } }, nowMs)

  cache = next
  cacheUserId = userId
  try {
    localStorage.setItem(storageKeyFor(userId), JSON.stringify(next))
  } catch {
    // Запись не удалась — остаёмся с копией в памяти. Осознанная деградация.
  }
  notify()
}

/** Непрочитана ли карточка: её версия новее последней отметки. */
export function isUnread(
  seen: SeenMap,
  requestNumber: string,
  updatedAt: string | null,
  createdAt: string | null,
): boolean {
  const source = updatedAt ?? createdAt
  const versionMs = source === null ? NaN : Date.parse(source)
  // Скобки вокруг `??` обязательны: `>` связывает сильнее, поэтому
  // `a > b ?? 0` вычислилось бы как `(a > b) ?? 0` и всегда давало false.
  return Number.isFinite(versionMs) && versionMs > (seen[requestNumber]?.versionMs ?? 0)
}

/** Только для тестов: сбросить рабочую копию, не трогая хранилище. */
export function __resetSeenForTests(): void {
  cache = null
  cacheUserId = null
  listeners.clear()
}
