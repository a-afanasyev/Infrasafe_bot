import { describe, expect, it, vi } from 'vitest'
import type { TFunction } from 'i18next'

import {
  AVATAR_GRADIENTS,
  SPEC_COLORS,
  getInitials,
  getSpecDisplay,
} from './employeeUtils'

// Identity t: returns the i18n key so we can assert mapping wiring.
const t = ((key: string) => key) as unknown as TFunction

describe('getInitials', () => {
  it('combines first+last initials uppercased', () => {
    expect(getInitials('ivan', 'petrov')).toBe('IP')
  })
  it('handles a single name', () => {
    expect(getInitials('ivan', null)).toBe('I')
    expect(getInitials(null, 'petrov')).toBe('P')
  })
  it('returns "?" when both are empty', () => {
    expect(getInitials(null, null)).toBe('?')
    expect(getInitials('', '')).toBe('?')
  })
})

describe('getSpecDisplay', () => {
  it('prefixes the emoji for a known specialization', () => {
    expect(getSpecDisplay('electrician', t)).toBe('⚡ specialization.electrician')
  })
  it('falls back to the raw value (no emoji) for an unknown key', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(getSpecDisplay('unknown_spec', t)).toBe('unknown_spec')
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})

describe('constants', () => {
  it('exposes avatar gradients and spec colors', () => {
    expect(AVATAR_GRADIENTS.length).toBeGreaterThan(0)
    expect(SPEC_COLORS.electrician).toBeTruthy()
  })
})
