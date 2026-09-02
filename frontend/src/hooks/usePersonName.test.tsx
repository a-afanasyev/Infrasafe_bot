import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { usePersonName } from './usePersonName'
import { useNameCaseStore } from '../stores/nameCaseStore'

beforeEach(() => {
  localStorage.clear()
  useNameCaseStore.setState({ mode: 'title' })
})

describe('usePersonName', () => {
  it('title по умолчанию: серверная строка и join полей', () => {
    const { result } = renderHook(() => usePersonName())
    expect(result.current.mode).toBe('title')
    expect(result.current.name('ИВАНОВ ИВАН')).toBe('Иванов Иван')
    expect(result.current.full({ first_name: 'ИВАН', last_name: 'ПЕТРОВ' })).toBe('Иван Петров')
  })

  it('переключение стора ре-рендерит хук в caps', () => {
    const { result } = renderHook(() => usePersonName())
    act(() => useNameCaseStore.getState().toggle())
    expect(result.current.mode).toBe('caps')
    expect(result.current.name('Иванов')).toBe('ИВАНОВ')
    expect(result.current.full({ first_name: 'Иван', last_name: 'Петров' })).toBe('ИВАН ПЕТРОВ')
  })

  it('fallback не форматируется', () => {
    const { result } = renderHook(() => usePersonName())
    act(() => useNameCaseStore.getState().setMode('caps'))
    expect(result.current.name('', 'Без имени')).toBe('Без имени')
    expect(result.current.name(null, '#12')).toBe('#12')
    expect(result.current.full(null, 'Без имени')).toBe('Без имени')
    expect(result.current.full({ first_name: null, last_name: '' }, 'ID 5')).toBe('ID 5')
  })

  it('без fallback пустое имя → ""', () => {
    const { result } = renderHook(() => usePersonName())
    expect(result.current.name(null)).toBe('')
    expect(result.current.full(undefined)).toBe('')
  })

  it('ссылки стабильны, пока режим не меняется', () => {
    const { result, rerender } = renderHook(() => usePersonName())
    const first = result.current
    rerender()
    expect(result.current.name).toBe(first.name)
    expect(result.current.full).toBe(first.full)
    act(() => useNameCaseStore.getState().toggle())
    expect(result.current.name).not.toBe(first.name)
  })
})
