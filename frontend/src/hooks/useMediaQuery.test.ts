import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useMediaQuery } from './useMediaQuery'

// TEST-068 Phase 2: useMediaQuery seeds from matchMedia(query).matches and
// updates on 'change' events. The global setup.ts stub is a static matches:false;
// here we install a controllable mock so we can drive a media change and assert
// the listener is wired (and torn down on unmount).
type ChangeHandler = (e: MediaQueryListEvent) => void

function installMatchMedia(initial: boolean) {
  const listeners = new Set<ChangeHandler>()
  const mql = {
    matches: initial,
    addEventListener: (_: string, h: ChangeHandler) => listeners.add(h),
    removeEventListener: (_: string, h: ChangeHandler) => listeners.delete(h),
  }
  window.matchMedia = vi.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia
  return {
    listeners,
    emit(matches: boolean) {
      mql.matches = matches
      listeners.forEach(h => h({ matches } as MediaQueryListEvent))
    },
  }
}

const original = window.matchMedia
afterEach(() => {
  window.matchMedia = original
})

describe('useMediaQuery', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('seeds the initial value from matchMedia().matches', () => {
    installMatchMedia(true)
    const { result } = renderHook(() => useMediaQuery('(min-width: 768px)'))
    expect(result.current).toBe(true)
  })

  it('updates when a change event fires', () => {
    const mm = installMatchMedia(false)
    const { result } = renderHook(() => useMediaQuery('(min-width: 768px)'))
    expect(result.current).toBe(false)
    act(() => mm.emit(true))
    expect(result.current).toBe(true)
  })

  it('removes its change listener on unmount', () => {
    const mm = installMatchMedia(false)
    const { unmount } = renderHook(() => useMediaQuery('(min-width: 768px)'))
    expect(mm.listeners.size).toBe(1)
    unmount()
    expect(mm.listeners.size).toBe(0)
  })
})
