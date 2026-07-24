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
  onopen: (() => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  close = vi.fn()

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
    FakeWebSocket.instances.at(-1)?.onclose?.({ code })
    await Promise.resolve() // дать отработать refreshSession().then(connect)
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
