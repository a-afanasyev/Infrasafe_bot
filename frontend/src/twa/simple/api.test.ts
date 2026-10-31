import { describe, it, expect, vi, beforeEach } from 'vitest'
import { queued } from '../../test/twaSimple'
import { sendQueued } from './api'

// Очередь одна, операций две: «Готово» → /complete, «Фото до» → /before-photo.

const { mockPost } = vi.hoisted(() => ({ mockPost: vi.fn() }))
vi.mock('../twaClient', () => ({ twaClient: { post: mockPost, get: vi.fn(), patch: vi.fn() } }))

beforeEach(() => {
  mockPost.mockReset()
  mockPost.mockResolvedValue({})
})

describe('sendQueued', () => {
  it.each([
    [undefined, '/api/v2/requests/260926-001/complete'],
    ['done' as const, '/api/v2/requests/260926-001/complete'],
    ['before' as const, '/api/v2/requests/260926-001/before-photo'],
  ])('kind=%s → %s, фото и тот же ключ', async (kind, url) => {
    const item = queued('260926-001', { kind })
    await sendQueued(item)
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [calledUrl, form] = mockPost.mock.calls[0] as [string, FormData]
    expect(calledUrl).toBe(url)
    expect(form.get('idempotency_key')).toBe(item.idempotencyKey)
    expect(form.get('photo')).toBeInstanceOf(File)
  })
})
