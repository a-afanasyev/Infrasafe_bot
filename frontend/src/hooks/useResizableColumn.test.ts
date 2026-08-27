import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useResizableColumn } from './useResizableColumn'

const KEY = 'test.colW'

describe('useResizableColumn — автоподбор ширины', () => {
  beforeEach(() => localStorage.removeItem(KEY))

  it('без сохранённой ширины действует autoWidth (с clamp)', () => {
    const { result } = renderHook(() =>
      useResizableColumn(KEY, 220, 140, 440, 350))
    expect(result.current.width).toBe(350)
  })

  it('autoWidth зажимается в max', () => {
    const { result } = renderHook(() =>
      useResizableColumn(KEY, 220, 140, 440, 900))
    expect(result.current.width).toBe(440)
  })

  it('сохранённая пользователем ширина ПОБЕЖДАЕТ автоподбор', () => {
    localStorage.setItem(KEY, '260')
    const { result } = renderHook(() =>
      useResizableColumn(KEY, 220, 140, 440, 350))
    expect(result.current.width).toBe(260)
  })

  it('без autoWidth — прежнее поведение (default)', () => {
    const { result } = renderHook(() =>
      useResizableColumn(KEY, 220, 140, 440))
    expect(result.current.width).toBe(220)
  })
})
