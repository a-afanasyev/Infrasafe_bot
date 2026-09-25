import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, act, waitFor } from '../../../test/test-utils'
import TaskTile from '../components/TaskTile'
import { limitMedia, MAX_PARALLEL } from './useLazyMedia'

// Фото плиток: грузим только видимые (IntersectionObserver) и не больше
// MAX_PARALLEL файлов разом — список на плохой сети не должен качать всё.

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet } }))

afterEach(() => {
  vi.unstubAllGlobals()
  mockGet.mockReset()
})

describe('limitMedia', () => {
  it(`не больше ${MAX_PARALLEL} параллельно, все выполняются`, async () => {
    let active = 0
    let peak = 0
    const task = (v: number) => () =>
      new Promise<number>((resolve) => {
        active += 1
        peak = Math.max(peak, active)
        setTimeout(() => {
          active -= 1
          resolve(v)
        }, 5)
      })
    const results = await Promise.all([1, 2, 3, 4, 5, 6, 7].map((v) => limitMedia(task(v))))
    expect(results).toEqual([1, 2, 3, 4, 5, 6, 7])
    expect(peak).toBe(MAX_PARALLEL)
  })
})

describe('ленивое фото плитки', () => {
  it('медиа заявки запрашивается только когда плитка видна', async () => {
    let fire: (visible: boolean) => void = () => {}
    class FakeObserver {
      constructor(cb: (entries: { isIntersecting: boolean }[]) => void) {
        fire = (visible) => cb([{ isIntersecting: visible }])
      }
      observe() {}
      disconnect() {}
    }
    vi.stubGlobal('IntersectionObserver', FakeObserver)
    mockGet.mockResolvedValue({ data: [] })
    render(<ul><TaskTile requestNumber="260926-001" category="plumbing" address="Дом 1" text="" /></ul>)
    expect(screen.getByText('Дом 1')).toBeInTheDocument()
    expect(mockGet).not.toHaveBeenCalled()
    act(() => fire(true))
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/api/v2/media/request/260926-001'))
  })
})
