import { describe, it, expect, afterEach, vi } from 'vitest'

// BRAND вычисляется на import-time из import.meta.env.VITE_BRAND, поэтому каждый
// кейс стабит env, сбрасывает кеш модулей и импортирует brand заново.
describe('brand config — build-time variant', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('defaults to infrasafe (dark, toggle allowed)', async () => {
    vi.stubEnv('VITE_BRAND', '')
    vi.resetModules()
    const { BRAND, brand } = await import('./brand')
    expect(BRAND).toBe('infrasafe')
    expect(brand.lightOnly).toBe(false)
    expect(brand.productTitle).toBe('UK Management')
    expect(brand.logoMark).toBe('infrasafe-logo.svg')
  })

  it('selects profk when VITE_BRAND=profk (light-only)', async () => {
    vi.stubEnv('VITE_BRAND', 'profk')
    vi.resetModules()
    const { BRAND, brand } = await import('./brand')
    expect(BRAND).toBe('profk')
    expect(brand.lightOnly).toBe(true)
    expect(brand.displayName).toBe('PROFK')
    expect(brand.logoMark).toBe('profk-mark.svg')
    expect(brand.boardBadge).toBe('PF')
  })

  it('falls back to infrasafe for an unknown brand value', async () => {
    vi.stubEnv('VITE_BRAND', 'nonsense')
    vi.resetModules()
    const { BRAND } = await import('./brand')
    expect(BRAND).toBe('infrasafe')
  })
})
