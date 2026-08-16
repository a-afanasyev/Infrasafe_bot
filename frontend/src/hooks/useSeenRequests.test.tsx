import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSeenRequests } from './useSeenRequests'
import { __resetSeenForTests, storageKeyFor } from '../components/kanban/seenRequests'
import { useAuthStore } from '../stores/authStore'

// Привязка чистого модуля отметок к React. Три вещи, каждая из которых ломает
// хук по-своему: локальные подписчики (иначе точка не гаснет в своей вкладке),
// слушатель `storage` (иначе не гаснет в соседней) и стабильный снапшот
// (иначе бесконечный ре-рендер).

beforeEach(() => {
  localStorage.clear()
  __resetSeenForTests()
  useAuthStore.setState({ user: { id: 42, roles: ['manager'] }, isAuthenticated: true })
})

describe('useSeenRequests', () => {
  it('карточка без отметки — непрочитанная', () => {
    const { result } = renderHook(() => useSeenRequests())

    expect(result.current.isUnread('260816-001', '2026-08-16T10:00:00Z', '2026-08-16T09:00:00Z')).toBe(true)
  })

  it('markSeen гасит точку в текущей вкладке без перезагрузки', () => {
    const { result } = renderHook(() => useSeenRequests())

    act(() => {
      result.current.markSeen('260816-001', '2026-08-16T10:00:00Z')
    })

    expect(result.current.isUnread('260816-001', '2026-08-16T10:00:00Z', null)).toBe(false)
  })

  it('реагирует на запись из соседней вкладки', () => {
    const { result } = renderHook(() => useSeenRequests())
    expect(result.current.isUnread('260816-001', '2026-08-16T10:00:00Z', null)).toBe(true)

    act(() => {
      localStorage.setItem(
        storageKeyFor(42),
        JSON.stringify({
          '260816-001': { versionMs: Date.parse('2026-08-16T10:00:00Z'), seenAtMs: Date.now() },
        }),
      )
      window.dispatchEvent(new StorageEvent('storage', { key: storageKeyFor(42) }))
    })

    expect(result.current.isUnread('260816-001', '2026-08-16T10:00:00Z', null)).toBe(false)
  })

  it('не ре-рендерится бесконечно (снапшот стабилен)', () => {
    let renders = 0
    renderHook(() => {
      renders++
      return useSeenRequests()
    })

    expect(renders).toBeLessThan(5)
  })

  it('без авторизованного пользователя markSeen молчит, а не падает', () => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
    const { result } = renderHook(() => useSeenRequests())

    act(() => {
      result.current.markSeen('260816-001', '2026-08-16T10:00:00Z')
    })

    expect(localStorage.length).toBe(0)
  })

  it('переключение пользователя не показывает чужие отметки', () => {
    const { result, rerender } = renderHook(() => useSeenRequests())
    act(() => {
      result.current.markSeen('260816-001', '2026-08-16T10:00:00Z')
    })

    act(() => {
      useAuthStore.setState({ user: { id: 7, roles: ['manager'] }, isAuthenticated: true })
    })
    rerender()

    expect(result.current.isUnread('260816-001', '2026-08-16T10:00:00Z', null)).toBe(true)
  })
})
