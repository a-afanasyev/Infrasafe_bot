import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useCan } from './useCan'
import { useAuthStore } from '@/stores/authStore'

// useCan читает действия из профиля в authStore. Это подсказка интерфейсу —
// решение принимает сервер на каждом запросе.
describe('useCan', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })

  it('true, если действие пришло в профиле', () => {
    useAuthStore.setState({ user: { id: 1, roles: ['manager'], actions: ['staff.manage'] }, isAuthenticated: true })
    expect(renderHook(() => useCan('staff.manage')).result.current).toBe(true)
  })

  it('false, если действия нет', () => {
    useAuthStore.setState({ user: { id: 1, roles: ['executor'], actions: ['requests.execute'] }, isAuthenticated: true })
    expect(renderHook(() => useCan('staff.manage')).result.current).toBe(false)
  })

  it('роль без действия ничего не открывает (решают действия, не роли)', () => {
    useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true })
    expect(renderHook(() => useCan('staff.manage')).result.current).toBe(false)
  })

  it('false без пользователя', () => {
    expect(renderHook(() => useCan('dashboard.use')).result.current).toBe(false)
  })
})
