import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useAccessSecurityFeed } from './useAccessSecurityFeed'
import { refreshSession } from '../api/client'

// F-04 (аудит 2026-07-11): access-WS закрывается по истечению JWT кодом 4001 —
// хук обновляет cookie-сессию и переподключается один раз; повторный 4001 в
// 30-секундном окне = refresh не помогает → статус error, без цикла.

vi.mock('../api/client', () => ({
  refreshSession: vi.fn(() => Promise.resolve()),
}))

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  send = vi.fn()
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
    await Promise.resolve() // дать отработать refreshSession().then(reconnect)
  })
}

async function closeWithOn(sock: FakeWebSocket, code: number) {
  await act(async () => {
    sock.onclose?.({ code })
    await Promise.resolve()
  })
}

describe('useAccessSecurityFeed — F-04 token expiry (4001)', () => {
  it('на 4001 обновляет сессию и переподключается', async () => {
    const { result } = renderHook(() => useAccessSecurityFeed())
    expect(FakeWebSocket.instances).toHaveLength(1)

    await closeWith(4001)

    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(result.current.status).toBe('connecting')
  })

  it('второй 4001 в 30-секундном окне → error, без повторного refresh', async () => {
    const { result } = renderHook(() => useAccessSecurityFeed())

    await closeWith(4001)
    await closeWith(4001)

    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(result.current.status).toBe('error')
  })

  it('на 1008 по-прежнему error без refresh (регрессия)', async () => {
    const { result } = renderHook(() => useAccessSecurityFeed())

    await closeWith(1008)

    expect(refreshSession).not.toHaveBeenCalled()
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(result.current.status).toBe('error')
  })

  it('провал refresh → error, без реконнекта', async () => {
    vi.mocked(refreshSession).mockRejectedValueOnce(new Error('logged out'))
    const { result } = renderHook(() => useAccessSecurityFeed())

    await closeWith(4001)

    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(result.current.status).toBe('error')
  })
})

// A9-P3-19: булев closedByCaller сбрасывался следующим mount'ом (StrictMode:
// mount → cleanup → mount), и поздний close ПЕРВОГО сокета, который браузер
// доставляет асинхронно, запускал реконнект — лишний сокет рядом с живым.
describe('useAccessSecurityFeed — поколение эффекта (StrictMode)', () => {
  it('поздний close сокета прошлого поколения не создаёт лишний сокет', async () => {
    vi.useFakeTimers()
    try {
      renderHook(() => useAccessSecurityFeed(), { reactStrictMode: true })
      expect(FakeWebSocket.instances).toHaveLength(2) // mount → cleanup → mount
      const stale = FakeWebSocket.instances[0]

      await act(async () => {
        stale.onclose?.({ code: 1006 })
        await vi.advanceTimersByTimeAsync(20_000)
      })

      expect(FakeWebSocket.instances).toHaveLength(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('поздний 4001 сокета прошлого поколения не дёргает refresh и не создаёт сокет', async () => {
    renderHook(() => useAccessSecurityFeed(), { reactStrictMode: true })
    await closeWithOn(FakeWebSocket.instances[0], 4001)
    expect(refreshSession).not.toHaveBeenCalled()
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('контроль: 4001 живого сокета по-прежнему обновляет сессию и переподключает', async () => {
    renderHook(() => useAccessSecurityFeed(), { reactStrictMode: true })
    await closeWithOn(FakeWebSocket.instances[1], 4001)
    expect(refreshSession).toHaveBeenCalledTimes(1)
    expect(FakeWebSocket.instances).toHaveLength(3)
  })
})
