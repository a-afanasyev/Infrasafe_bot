import { afterEach, describe, expect, it } from 'vitest'

import { getTWAInitData, isTWA } from './isTWA'

afterEach(() => {
  delete (window as { Telegram?: unknown }).Telegram
})

describe('isTWA', () => {
  it('is false outside Telegram', () => {
    delete (window as { Telegram?: unknown }).Telegram
    expect(isTWA()).toBe(false)
  })

  it('is false when WebApp has no initData', () => {
    ;(window as { Telegram?: unknown }).Telegram = { WebApp: { initData: '' } }
    expect(isTWA()).toBe(false)
  })

  it('is true with non-empty initData', () => {
    ;(window as { Telegram?: unknown }).Telegram = { WebApp: { initData: 'auth=1' } }
    expect(isTWA()).toBe(true)
  })
})

describe('getTWAInitData', () => {
  it('returns the initData string', () => {
    ;(window as { Telegram?: unknown }).Telegram = { WebApp: { initData: 'auth=1' } }
    expect(getTWAInitData()).toBe('auth=1')
  })

  it('returns empty string outside Telegram', () => {
    delete (window as { Telegram?: unknown }).Telegram
    expect(getTWAInitData()).toBe('')
  })
})
