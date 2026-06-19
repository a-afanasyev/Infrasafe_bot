import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useHasRole } from './useHasRole'
import { useAuthStore } from '@/stores/authStore'

// TEST-068 Phase 2: useHasRole reads UI-facing roles from authStore. Gating is
// `roles?.includes(role) ?? false` — null user / missing roles → false.
beforeEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false, hydrating: false })
})

describe('useHasRole', () => {
  it('returns false when no user is set', () => {
    const { result } = renderHook(() => useHasRole('manager'))
    expect(result.current).toBe(false)
  })

  it('returns true when the user carries the role', () => {
    useAuthStore.setState({ user: { id: 1, roles: ['manager', 'executor'] }, isAuthenticated: true })
    const { result } = renderHook(() => useHasRole('executor'))
    expect(result.current).toBe(true)
  })

  it('returns false when the user lacks the role', () => {
    useAuthStore.setState({ user: { id: 1, roles: ['applicant'] }, isAuthenticated: true })
    const { result } = renderHook(() => useHasRole('manager'))
    expect(result.current).toBe(false)
  })

  it('returns false when roles array is empty', () => {
    useAuthStore.setState({ user: { id: 1, roles: [] }, isAuthenticated: true })
    const { result } = renderHook(() => useHasRole('manager'))
    expect(result.current).toBe(false)
  })
})
