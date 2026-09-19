import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { renderHook } from '@testing-library/react'
import { render, screen } from '../test/test-utils'
import { server } from '../test/msw/server'
import { useTheme } from './useTheme'
import { useResizableColumn } from './useResizableColumn'
import AutoManagerCard from '../components/shifts/AutoManagerCard'

// AUD8-FE-05: доступ к localStorage бросает (Safari private, sandboxed iframe) —
// хуки/карточка должны работать с дефолтами, а не падать при рендере.

beforeEach(() => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('denied', 'SecurityError') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('denied', 'QuotaExceededError') })
})
afterEach(() => vi.restoreAllMocks())

describe('устойчивость к недоступному localStorage', () => {
  it('useTheme: дефолт и toggle без исключений', () => {
    const { result } = renderHook(() => useTheme())
    expect(typeof result.current.isDark).toBe('boolean')
    expect(() => result.current.toggle()).not.toThrow()
  })

  it('useResizableColumn: дефолтная ширина', () => {
    const { result } = renderHook(() => useResizableColumn('uk.test.col', 220))
    expect(result.current.width).toBe(220)
  })

  it('AutoManagerCard рендерится свёрнутым по умолчанию', async () => {
    server.use(http.get('*/api/v2/auto-manager-config', () => HttpResponse.json({ enabled: false, window_start: '22:00', window_end: '06:00' })))
    render(<AutoManagerCard />)
    expect(await screen.findByRole('button')).toBeInTheDocument()
  })
})
