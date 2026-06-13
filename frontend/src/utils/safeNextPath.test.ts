import { describe, it, expect } from 'vitest'
import { safeNextPath } from './safeNextPath'

describe('safeNextPath — open-redirect guard for ?next=', () => {
  it('passes through same-origin absolute paths (incl. query)', () => {
    expect(safeNextPath('/dashboard')).toBe('/dashboard')
    expect(safeNextPath('/dashboard?request=260101-001')).toBe('/dashboard?request=260101-001')
  })

  it('falls back to /dashboard for null/empty', () => {
    expect(safeNextPath(null)).toBe('/dashboard')
    expect(safeNextPath('')).toBe('/dashboard')
  })

  it('rejects protocol-relative and absolute URLs (off-site redirect)', () => {
    expect(safeNextPath('//evil.com')).toBe('/dashboard')
    expect(safeNextPath('//evil.com/path')).toBe('/dashboard')
    expect(safeNextPath('https://evil.com')).toBe('/dashboard')
    expect(safeNextPath('http://evil.com')).toBe('/dashboard')
  })

  it('rejects relative paths without a leading slash', () => {
    expect(safeNextPath('dashboard')).toBe('/dashboard')
    expect(safeNextPath('javascript:alert(1)')).toBe('/dashboard')
  })
})
