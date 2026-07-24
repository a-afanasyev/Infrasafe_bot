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
