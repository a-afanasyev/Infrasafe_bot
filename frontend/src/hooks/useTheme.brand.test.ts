import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Light-only бренд (PROFK) держит светлую тему принудительно. brand.lightOnly
// вычисляется на import-time, поэтому стабим VITE_BRAND=profk и импортируем
// useTheme заново (он подтянет свежий brand-модуль).
describe('useTheme — light-only brand (PROFK)', () => {
  beforeEach(() => {
    localStorage.clear()
    document.body.classList.remove('light')
    vi.stubEnv('VITE_BRAND', 'profk')
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('forces light regardless of stored dark preference and hides toggle', async () => {
    localStorage.setItem('theme', 'dark')
    const { useTheme } = await import('./useTheme')
    const { result } = renderHook(() => useTheme())

    expect(result.current.isDark).toBe(false)
    expect(result.current.canToggle).toBe(false)
    expect(document.body.classList.contains('light')).toBe(true)
  })

  it('toggle is a no-op and does not touch localStorage', async () => {
    const { useTheme } = await import('./useTheme')
    const { result } = renderHook(() => useTheme())

    act(() => result.current.toggle())

    expect(result.current.isDark).toBe(false)
    expect(document.body.classList.contains('light')).toBe(true)
    expect(localStorage.getItem('theme')).toBeNull()
  })
})
