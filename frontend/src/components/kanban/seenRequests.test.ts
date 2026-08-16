import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import {
  SEEN_TTL_MS,
  SEEN_MAX_ENTRIES,
  isUnread,
  markSeen,
  readSeen,
  storageKeyFor,
  subscribeSeen,
  __resetSeenForTests,
} from './seenRequests'

// «Прочитано» живёт только в браузере (решение владельца — серверной модели нет).
// Модуль чистый: вся работа с localStorage изолирована здесь, компоненты знают
// только про булев `unread`.

const USER = 42
const DAY = 24 * 60 * 60 * 1000

beforeEach(() => {
  localStorage.clear()
  __resetSeenForTests()
  vi.useRealTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('storageKeyFor', () => {
  it('разделяет пользователей', () => {
    expect(storageKeyFor(1)).not.toBe(storageKeyFor(2))
    expect(storageKeyFor(1)).toContain('uk_kanban_seen_v1')
  })
})

describe('isUnread', () => {
  it('карточка без отметки — непрочитанная', () => {
    expect(isUnread({}, '260816-001', '2026-08-16T10:00:00Z', null)).toBe(true)
  })

  it('отметка старше текущей версии — снова непрочитанная', () => {
    const seen = { '260816-001': { versionMs: Date.parse('2026-08-16T10:00:00Z'), seenAtMs: 1 } }

    expect(isUnread(seen, '260816-001', '2026-08-16T11:00:00Z', null)).toBe(true)
  })

  it('отметка на текущей версии — прочитанная', () => {
    const versionMs = Date.parse('2026-08-16T11:00:00Z')
    const seen = { '260816-001': { versionMs, seenAtMs: 1 } }

    expect(isUnread(seen, '260816-001', '2026-08-16T11:00:00Z', null)).toBe(false)
  })

  it('updated_at = null — берём created_at', () => {
    // У нетронутых строк updated_at пустой (onupdate срабатывает только при
    // изменении). Без фолбэка Date.parse(null) дал бы NaN, и новая заявка
    // никогда не подсветилась бы.
    expect(isUnread({}, '260816-001', null, '2026-08-16T09:00:00Z')).toBe(true)
  })

  it('обе даты пустые — не непрочитанная, а не NaN-мусор', () => {
    expect(isUnread({}, '260816-001', null, null)).toBe(false)
  })

  it('нечитаемая дата не делает карточку непрочитанной', () => {
    expect(isUnread({}, '260816-001', 'не-дата', null)).toBe(false)
  })
})

describe('markSeen', () => {
  it('записывает версию и время отметки', () => {
    markSeen(USER, '260816-001', '2026-08-16T11:00:00Z')

    const seen = readSeen(USER)
    expect(seen['260816-001'].versionMs).toBe(Date.parse('2026-08-16T11:00:00Z'))
    expect(seen['260816-001'].seenAtMs).toBeGreaterThan(0)
  })

  it('не откатывает отметку назад при повторе со старой версией', () => {
    markSeen(USER, '260816-001', '2026-08-16T11:00:00Z')
    markSeen(USER, '260816-001', '2026-08-16T10:00:00Z')

    expect(readSeen(USER)['260816-001'].versionMs).toBe(Date.parse('2026-08-16T11:00:00Z'))
  })

  it('игнорирует нечитаемую дату вместо записи NaN', () => {
    markSeen(USER, '260816-001', 'не-дата')

    expect(readSeen(USER)['260816-001']).toBeUndefined()
  })

  it('чистит записи старше TTL', () => {
    const stale = {
      'old-001': { versionMs: 1, seenAtMs: Date.now() - SEEN_TTL_MS - DAY },
      'fresh-001': { versionMs: 1, seenAtMs: Date.now() },
    }
    localStorage.setItem(storageKeyFor(USER), JSON.stringify(stale))
    __resetSeenForTests()

    markSeen(USER, '260816-001', '2026-08-16T11:00:00Z')

    const seen = readSeen(USER)
    expect(seen['old-001']).toBeUndefined()
    expect(seen['fresh-001']).toBeDefined()
  })

  it('держит потолок записей, выбрасывая самые старые', () => {
    const many: Record<string, { versionMs: number; seenAtMs: number }> = {}
    for (let i = 0; i < SEEN_MAX_ENTRIES + 50; i++) {
      many[`n-${i}`] = { versionMs: 1, seenAtMs: Date.now() - (SEEN_MAX_ENTRIES + 50 - i) * 1000 }
    }
    localStorage.setItem(storageKeyFor(USER), JSON.stringify(many))
    __resetSeenForTests()

    markSeen(USER, '260816-001', '2026-08-16T11:00:00Z')

    const seen = readSeen(USER)
    expect(Object.keys(seen).length).toBeLessThanOrEqual(SEEN_MAX_ENTRIES)
    expect(seen['260816-001']).toBeDefined()
    expect(seen['n-0'], 'самая старая запись должна вылететь первой').toBeUndefined()
  })
})

describe('деградация при недоступном localStorage', () => {
  it('продолжает гасить точки в памяти, а не выключает фичу', () => {
    // Приватный режим/квота: запись бросает. «Точек нет» — худшая из
    // деградаций, она молча выключает фичу; правильная — работа в памяти.
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota')
    })
    try {
      markSeen(USER, '260816-001', '2026-08-16T11:00:00Z')

      expect(readSeen(USER)['260816-001']).toBeDefined()
    } finally {
      setItem.mockRestore()
    }
  })

  it('битый JSON в хранилище не роняет чтение', () => {
    localStorage.setItem(storageKeyFor(USER), '{не json')
    __resetSeenForTests()

    expect(readSeen(USER)).toEqual({})
  })
})

describe('подписки', () => {
  it('уведомляет подписчиков ТЕКУЩЕЙ вкладки', () => {
    // Событие `storage` в своей вкладке не срабатывает — без локального
    // уведомления точка не гасла бы до перезагрузки.
    const seenCb = vi.fn()
    const unsubscribe = subscribeSeen(seenCb)

    markSeen(USER, '260816-001', '2026-08-16T11:00:00Z')

    expect(seenCb).toHaveBeenCalled()
    unsubscribe()
  })

  it('отписка действительно отписывает', () => {
    const seenCb = vi.fn()
    subscribeSeen(seenCb)()

    markSeen(USER, '260816-001', '2026-08-16T11:00:00Z')

    expect(seenCb).not.toHaveBeenCalled()
  })

  it('readSeen отдаёт стабильную ссылку, пока не было записи', () => {
    // useSyncExternalStore сравнивает снапшоты по ссылке: новый объект на
    // каждый вызов = бесконечный ре-рендер.
    expect(readSeen(USER)).toBe(readSeen(USER))

    markSeen(USER, '260816-001', '2026-08-16T11:00:00Z')

    expect(readSeen(USER)).toBe(readSeen(USER))
  })
})
