import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePageTitle } from './usePageTitle'

// TEST-068 Phase 2: usePageTitle syncs document.title in an effect. A non-empty
// title is suffixed with the app name; an empty title falls back to the bare name.
describe('usePageTitle', () => {
  it('sets a suffixed document.title for a non-empty title', () => {
    renderHook(() => usePageTitle('Заявки'))
    expect(document.title).toBe('Заявки — UK Management')
  })

  it('falls back to the bare app name for an empty title', () => {
    renderHook(() => usePageTitle(''))
    expect(document.title).toBe('UK Management')
  })

  it('re-syncs the title when the prop changes', () => {
    const { rerender } = renderHook(({ t }) => usePageTitle(t), {
      initialProps: { t: 'Смены' },
    })
    expect(document.title).toBe('Смены — UK Management')
    rerender({ t: 'Адреса' })
    expect(document.title).toBe('Адреса — UK Management')
  })
})
