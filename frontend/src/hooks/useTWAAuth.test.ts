import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'

// FE-05: сбой TWA-аутентификации раньше проглатывался (.catch(console.error))
// — страница оставалась пустой. Хук обязан вернуть isError + retry.

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  login: vi.fn(async () => {}),
}))

vi.mock('../api/client', () => ({
  apiClient: { post: vi.fn() },
  publicClient: { post: mocks.post },
}))
vi.mock('../utils/isTWA', () => ({
  isTWA: () => true,
  getTWAInitData: () => 'stub-init-data',
}))
vi.mock('../stores/authStore', () => ({
  useAuthStore: () => ({ isAuthenticated: false, login: mocks.login }),
}))

import { useTWAAuth } from './useTWAAuth'

describe('useTWAAuth (FE-05)', () => {
  beforeEach(() => {
    mocks.post.mockReset()
    mocks.login.mockClear()
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('сбой аутентификации → isError=true, isLoading=false (не пустой экран)', async () => {
    mocks.post.mockRejectedValueOnce(new Error('network down'))

    const { result } = renderHook(() => useTWAAuth())

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.isLoading).toBe(false)
    expect(mocks.login).not.toHaveBeenCalled()
  })

  it('retry() повторяет попытку и сбрасывает isError при успехе', async () => {
    mocks.post.mockRejectedValueOnce(new Error('network down'))
    mocks.post.mockResolvedValueOnce({ data: {} })

    const { result } = renderHook(() => useTWAAuth())
    await waitFor(() => expect(result.current.isError).toBe(true))

    act(() => result.current.retry())

    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(result.current.isError).toBe(false))
    expect(mocks.login).toHaveBeenCalledTimes(1)
  })

  it('успешная аутентификация — login() вызван, ошибки нет', async () => {
    mocks.post.mockResolvedValueOnce({ data: {} })

    const { result } = renderHook(() => useTWAAuth())

    await waitFor(() => expect(mocks.login).toHaveBeenCalledTimes(1))
    expect(result.current.isError).toBe(false)
  })

  it('FE-06: в консоль уходит только message, не объект ошибки с initData', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    spy.mockClear() // вызовы из предыдущих тестов не считаем
    mocks.post.mockRejectedValueOnce(new Error('boom'))

    renderHook(() => useTWAAuth())

    await waitFor(() => expect(spy).toHaveBeenCalled())
    const args = spy.mock.calls.find(c => c[0] === 'TWA auth failed:')
    expect(args).toBeDefined()
    expect(typeof args![1]).toBe('string')
    expect(args![1]).toBe('boom')
  })
})
