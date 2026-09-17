import { describe, it, expect } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useDebouncedValue } from './useDebouncedValue'

describe('useDebouncedValue', () => {
  it('отдаёт новое значение только после паузы', async () => {
    const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 50), {
      initialProps: { v: 'a' },
    })
    expect(result.current).toBe('a')
    rerender({ v: 'ab' })
    expect(result.current).toBe('a')
    await act(async () => {
      await new Promise(r => setTimeout(r, 80))
    })
    expect(result.current).toBe('ab')
  })
})
