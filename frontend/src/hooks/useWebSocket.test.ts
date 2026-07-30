import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useWebSocket } from './useWebSocket'
import { refreshSession } from '../api/client'

// F-04 (аудит 2026-07-11): сервер закрывает WS по истечению JWT кодом 4001 —
// хук обязан обновить cookie-сессию (refreshSession) и переподключиться один
// раз, не зацикливая refresh и не трогая поведение 1008 (стоп без ретраев).

vi.mock('../api/client', () => ({
  refreshSession: vi.fn(() => Promise.resolve()),
}))

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  // readyState нужен по-настоящему: восстановление по online/visibilitychange
  // обязано НЕ дублировать живой сокет, а без этого поля проверить это нечем.
  readyState = 0 // CONNECTING
  onopen: (() => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  // close() обязан переводить сокет в CLOSED: иначе после размонтирования фейк
  // остаётся «живым», и тест на снятие слушателей проходил бы даже при утечке.
  close = vi.fn(() => { this.readyState = 3 })

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
}

beforeEach(() => {
  FakeWebSocket.instances = []
  vi.mocked(refreshSession).mockClear()
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function closeWith(code: number) {
  await act(async () => {
    const sock = FakeWebSocket.instances.at(-1)
    if (sock) sock.readyState = 3 // CLOSED — иначе «оживление» решит, что сокет жив
    sock?.onclose?.({ code })
    await Promise.resolve() // дать отработать refreshSession().then(connect)
  })
}

/** Успешный upgrade: с этого момента 1006 означает сетевой обрыв, а не отказ. */
async function openLast() {
  await act(async () => {
    const sock = FakeWebSocket.instances.at(-1)
    if (sock) sock.readyState = 1 // OPEN
    sock?.onopen?.()
  })
}

describe('useWebSocket — F-04 token expiry (4001)', () => {
  it('на 4001 обновляет сессию и переподключается', async () => {
    renderHook(() => useWebSocket('kanban', () => {}))
    expect(FakeWebSocket.instances).toHaveLength(1)

    await closeWith(4001)

    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('второй 4001 в 30-секундном окне не запускает повторный refresh (нет цикла)', async () => {
    renderHook(() => useWebSocket('kanban', () => {}))

    await closeWith(4001)
    await closeWith(4001) // сразу же — свежий токен обязан жить ~60 мин

    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(2) // второго реконнекта нет
  })

  it('на 1008 не делает ни refresh, ни reconnect (регрессия)', async () => {
    renderHook(() => useWebSocket('kanban', () => {}))

    await closeWith(1008)

    expect(refreshSession).not.toHaveBeenCalled()
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('провал refresh не роняет хук и не реконнектит', async () => {
    vi.mocked(refreshSession).mockRejectedValueOnce(new Error('logged out'))
    renderHook(() => useWebSocket('kanban', () => {}))

    await closeWith(4001)

    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(1) // редирект на /login — не наша забота
  })
})

// F-04 (остаток): 4003 — доступ отозван УЖЕ во время сессии (блокировка или
// снятие роли). В отличие от 4001 обновление сессии тут бессмысленно: новый
// токен выдадут тому же заблокированному пользователю. Без отдельной ветки код
// попадал бы в общий реконнект и клиент долбился бы в сервер до отказа.
describe('useWebSocket — F-04 access revoked (4003)', () => {
  it('на 4003 не обновляет сессию и не переподключается', async () => {
    // Фейковые таймеры обязательны: реконнект отложен на 3 с, и без прокрутки
    // времени тест был бы зелёным независимо от наличия ветки 4003.
    vi.useFakeTimers()
    try {
      renderHook(() => useWebSocket('kanban', () => {}))

      await closeWith(4003)
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })

      expect(refreshSession).not.toHaveBeenCalled()
      expect(FakeWebSocket.instances).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('контроль: сетевой обрыв (1006) переподключается — общая ветка жива', async () => {
    vi.useFakeTimers()
    try {
      renderHook(() => useWebSocket('kanban', () => {}))
      // onopen обязателен: 1006 ПОСЛЕ успешного upgrade — это сетевой обрыв, а
      // 1006 ДО него — pre-upgrade отказ сервера, и это разные ветки (см. ниже).
      await openLast()

      await closeWith(1006)
      await act(async () => { await vi.advanceTimersByTimeAsync(3_500) })

      expect(FakeWebSocket.instances).toHaveLength(2)
      expect(refreshSession).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })
})

// П4: отказ ДО upgrade. Сервер закрывает соединение до accept() → uvicorn
// отвечает HTTP 403, close-кадра нет, браузер видит 1006 и НЕ вызывает onopen
// (контракт провода прибит в tests/api/test_ws_wire_protocol.py). HTTP-статус
// браузерный WebSocket API не отдаёт, поэтому «просроченная cookie» и «сервер
// недоступен» для клиента выглядят одинаково — единственный доступный признак
// это «закрылось, ни разу не открывшись».
describe('useWebSocket — отказ до upgrade (1006 без onopen)', () => {
  it('обновляет сессию и переподключается', async () => {
    renderHook(() => useWebSocket('kanban', () => {}))
    expect(FakeWebSocket.instances).toHaveLength(1)

    await closeWith(1006) // onopen не вызывался

    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('второй отказ в 30-секундном окне не повторяет refresh (нет цикла при мёртвом сервере)', async () => {
    vi.useFakeTimers()
    try {
      renderHook(() => useWebSocket('kanban', () => {}))

      await closeWith(1006)
      await closeWith(1006)
      await act(async () => { await vi.advanceTimersByTimeAsync(3_500) })

      expect(refreshSession).toHaveBeenCalledTimes(1)
      // второй отказ уходит в обычный backoff, а не в ещё один refresh
      expect(FakeWebSocket.instances).toHaveLength(3)
    } finally {
      vi.useRealTimers()
    }
  })
})

// AUD5-APIFE-7: после MAX_RECONNECT_ATTEMPTS хук замолкал навсегда. Ноутбук
// уснул или пропал wifi → доска мертва до перезагрузки страницы, хотя браузер
// прямо сообщает о возврате связи (online) и о возврате пользователя
// (visibilitychange).
describe('useWebSocket — восстановление по online / visibilitychange', () => {
  /** Довести хук до состояния «сдался»: закрывать, пока он ещё переподключается.
   *
   * Считать обрывы по числу — ловушка: последний из них оставляет сокет в
   * CONNECTING, и тогда «оживление» законно его не дублирует, а тест краснеет
   * не на том. Условие выхода — сам факт, что новых сокетов больше не создаётся.
   */
  async function exhaustAttempts() {
    await openLast() // 1-й обрыв должен читаться как сетевой, а не как отказ
    for (let i = 0; i < 20; i += 1) {
      const before = FakeWebSocket.instances.length
      await closeWith(1006)
      await act(async () => { await vi.advanceTimersByTimeAsync(3_500) })
      if (FakeWebSocket.instances.length === before) return
    }
    throw new Error('хук не перестал переподключаться — MAX_RECONNECT_ATTEMPTS не работает')
  }

  it('online обнуляет счётчик попыток и переподключает', async () => {
    vi.useFakeTimers()
    try {
      renderHook(() => useWebSocket('kanban', () => {}))
      await exhaustAttempts()
      const exhausted = FakeWebSocket.instances.length

      await act(async () => { window.dispatchEvent(new Event('online')) })

      expect(FakeWebSocket.instances.length).toBe(exhausted + 1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('возврат вкладки в видимое состояние переподключает мёртвое соединение', async () => {
    vi.useFakeTimers()
    try {
      renderHook(() => useWebSocket('kanban', () => {}))
      await exhaustAttempts()
      const exhausted = FakeWebSocket.instances.length

      await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })

      expect(FakeWebSocket.instances.length).toBe(exhausted + 1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('online при живом соединении не создаёт второй сокет', async () => {
    renderHook(() => useWebSocket('kanban', () => {}))
    await openLast()

    await act(async () => { window.dispatchEvent(new Event('online')) })

    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('после размонтирования события больше не поднимают соединений', async () => {
    const { unmount } = renderHook(() => useWebSocket('kanban', () => {}))
    await openLast()
    unmount()

    await act(async () => { window.dispatchEvent(new Event('online')) })

    expect(FakeWebSocket.instances).toHaveLength(1)
  })
})

// AUD6-P2-13: cleanup закрывает сокет и таймер, но промис refreshSession()
// он отменить не может — до guard'а resolve после размонтирования создавал
// новый сокет, который уже никто не закрывал (утечка соединения + подписка
// Redis на стороне сервера до exp).
describe('useWebSocket — unmount во время refresh', () => {
  it('resolve зависшего refresh после unmount не создаёт новый сокет', async () => {
    let resolveRefresh!: () => void
    vi.mocked(refreshSession).mockImplementationOnce(
      () => new Promise<void>((res) => { resolveRefresh = res }),
    )
    const { unmount } = renderHook(() => useWebSocket('kanban', () => {}))
    expect(FakeWebSocket.instances).toHaveLength(1)

    await closeWith(4001) // refresh завис в полёте
    expect(FakeWebSocket.instances).toHaveLength(1)

    unmount()
    await act(async () => {
      resolveRefresh()
      await Promise.resolve()
    })

    expect(FakeWebSocket.instances).toHaveLength(1) // нового сокета нет
  })

  it('без unmount тот же зависший refresh ПОСЛЕ resolve переподключается (контроль)', async () => {
    let resolveRefresh!: () => void
    vi.mocked(refreshSession).mockImplementationOnce(
      () => new Promise<void>((res) => { resolveRefresh = res }),
    )
    renderHook(() => useWebSocket('kanban', () => {}))

    await closeWith(4001)
    expect(FakeWebSocket.instances).toHaveLength(1) // ещё ждём refresh

    await act(async () => {
      resolveRefresh()
      await Promise.resolve()
    })

    expect(FakeWebSocket.instances).toHaveLength(2) // guard не задушил живой путь
  })
})
