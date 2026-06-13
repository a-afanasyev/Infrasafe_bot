import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTheme } from './useTheme'

// PR-20 / FE-08: the effect is the single source syncing the DOM class to
// `isDark` (handler no longer toggles it manually + missing-dep removed).
describe('useTheme — FE-08', () => {
  beforeEach(() => {
    localStorage.clear()
    document.body.classList.remove('light')
  })

  it('defaults to dark when no stored preference', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.isDark).toBe(true)
    expect(document.body.classList.contains('light')).toBe(false)
  })

  it('reads stored light preference and syncs body class on mount', () => {
    localStorage.setItem('theme', 'light')
    const { result } = renderHook(() => useTheme())
    expect(result.current.isDark).toBe(false)
    expect(document.body.classList.contains('light')).toBe(true)
  })

  it('toggle flips isDark, syncs body class via effect, and persists', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.isDark).toBe(true)

    act(() => result.current.toggle())
    expect(result.current.isDark).toBe(false)
    expect(document.body.classList.contains('light')).toBe(true)
    expect(localStorage.getItem('theme')).toBe('light')

    act(() => result.current.toggle())
    expect(result.current.isDark).toBe(true)
    expect(document.body.classList.contains('light')).toBe(false)
    expect(localStorage.getItem('theme')).toBe('dark')
  })
})
