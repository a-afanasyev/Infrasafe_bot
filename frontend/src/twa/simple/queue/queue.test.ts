import { describe, it, expect, vi } from 'vitest'
import { attemptSend, createQueueItem } from './engine'
import {
  FOREIGN_TTL_MS,
  classifyCompletionError,
  dueItems,
  newIdempotencyKey,
  nextWakeDelay,
  ownItems,
  pendingNumbers,
  retryDelay,
  staleForeign,
} from './policy'
import { createMemoryStore, openQueueStore } from './store'

// Очередь «Готово» простого режима: фото и ключ идемпотентности живут в
// хранилище до доставки; временные сбои повторяются по расписанию
// 5 с → 15 с → 60 с → каждые 2 мин, окончательные отказы помечаются failed.

const httpError = (status: number, detail?: string) => ({ response: { status, data: { detail } } })
const photo = () => new Blob(['jpeg'], { type: 'image/jpeg' })
const make = (requestNumber: string, now = 0, userId = 1, key?: string) =>
  createQueueItem({ userId, requestNumber, photo: photo(), fileName: 'a.jpg' }, now, key)

describe('retryDelay', () => {
  it('5 с → 15 с → 60 с → далее каждые 2 минуты', () => {
    expect([1, 2, 3, 4, 5, 20].map(retryDelay)).toEqual([5_000, 15_000, 60_000, 120_000, 120_000, 120_000])
  })
})

describe('classifyCompletionError', () => {
  it.each([
    ['нет сети', { message: 'Network Error' }],
    ['408', httpError(408)],
    ['429', httpError(429)],
    ['500', httpError(500)],
    ['502 от edge без кода', httpError(502)],
    ['503 media_unavailable', httpError(503, 'media_unavailable')],
    ['409 in_progress (тот же ключ ещё обрабатывается)', httpError(409, 'in_progress')],
  ])('%s — повторять', (_name, err) => {
    expect(classifyCompletionError(err)).toEqual({ kind: 'retry', noShift: false })
  })

  it('403 no_active_shift — повторять (начнёт смену — уйдёт без пересъёмки)', () => {
    expect(classifyCompletionError(httpError(403, 'no_active_shift'))).toEqual({ kind: 'retry', noShift: true })
  })

  it.each([
    [httpError(409, 'invalid_status'), 'closed'],
    [httpError(403, 'not_assigned'), 'not_yours'],
    [httpError(404), 'not_yours'],
    [httpError(413, 'photo_too_large'), 'bad_photo'],
    [httpError(415, 'unsupported_photo_type'), 'bad_photo'],
    [httpError(422, 'photo_empty'), 'bad_photo'],
    [httpError(502, 'media_rejected'), 'bad_photo'],
  ])('%o — окончательно (%s)', (err, reason) => {
    expect(classifyCompletionError(err)).toEqual({ kind: 'final', reason })
  })
})

describe('расписание и отбор', () => {
  it('nextWakeDelay — до ближайшего срока; ждущие смены и проваленные не будят', () => {
    const a = { ...make('1'), nextAttemptAt: 5_000 }
    const b = { ...make('2'), nextAttemptAt: 2_000 }
    const noShift = { ...make('3'), nextAttemptAt: 100, noShift: true }
    const failed = { ...make('4'), nextAttemptAt: 100, failed: 'bad_photo' as const }
    expect(nextWakeDelay([a, b, noShift, failed], 1_000)).toBe(1_000)
    expect(nextWakeDelay([a, b], 9_000)).toBe(0)
    expect(nextWakeDelay([noShift, failed], 0)).toBeNull()
    expect(dueItems([a, b, noShift, failed], 3_000).map((i) => i.requestNumber)).toEqual(['2'])
    expect(pendingNumbers([a, b, noShift, failed])).toEqual(new Set(['1', '2', '3']))
  })

  it('записи другого пользователя не свои; чужие старше 7 дней — на удаление', () => {
    const mine = make('1', 0, 1)
    const fresh = make('2', 10, 2)
    const old = make('3', 0, 2)
    const now = FOREIGN_TTL_MS + 5
    expect(ownItems([mine, fresh, old], 1)).toEqual([mine])
    expect(ownItems([mine], null)).toEqual([])
    expect(staleForeign([mine, fresh, old], 1, now)).toEqual([old])
  })

  it('ключ идемпотентности — UUID v4, в т.ч. без crypto.randomUUID', () => {
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    expect(newIdempotencyKey()).toMatch(uuid)
    const original = globalThis.crypto.randomUUID
    Object.defineProperty(globalThis.crypto, 'randomUUID', { value: undefined, configurable: true, writable: true })
    try {
      expect(newIdempotencyKey()).toMatch(uuid)
    } finally {
      Object.defineProperty(globalThis.crypto, 'randomUUID', { value: original, configurable: true, writable: true })
    }
  })
})

describe('attemptSend', () => {
  it('успех — запись удаляется', async () => {
    const store = createMemoryStore()
    const item = make('260926-001')
    await store.put(item)
    const send = vi.fn().mockResolvedValue({})
    expect(await attemptSend(store, item, send)).toEqual({ kind: 'sent' })
    expect(send).toHaveBeenCalledWith(item)
    expect(await store.list()).toEqual([])
  })

  it('сбой сети — запись остаётся с тем же ключом, счётчиком и сроком по расписанию', async () => {
    const store = createMemoryStore()
    const item = make('260926-001', 0, 1, '11111111-1111-4111-8111-111111111111')
    await store.put(item)
    const send = vi.fn().mockRejectedValueOnce({ message: 'Network Error' }).mockRejectedValueOnce(httpError(503))
    let now = 1_000
    expect(await attemptSend(store, item, send, () => now)).toEqual({ kind: 'queued', noShift: false })
    let [stored] = await store.list()
    expect(stored).toMatchObject({ idempotencyKey: item.idempotencyKey, attempts: 1, nextAttemptAt: 6_000 })

    now = 6_000
    await attemptSend(store, stored, send, () => now)
    ;[stored] = await store.list()
    expect(stored).toMatchObject({ attempts: 2, nextAttemptAt: 21_000 })

    send.mockResolvedValueOnce({})
    expect(await attemptSend(store, stored, send)).toEqual({ kind: 'sent' })
    expect(send.mock.calls.map(([i]) => i.idempotencyKey)).toEqual(Array(3).fill(item.idempotencyKey))
    expect(await store.list()).toEqual([])
  })

  it('нет смены — запись с флагом noShift (таймер её не трогает)', async () => {
    const store = createMemoryStore()
    const item = make('260926-001')
    await store.put(item)
    await attemptSend(store, item, vi.fn().mockRejectedValue(httpError(403, 'no_active_shift')))
    expect((await store.list())[0]).toMatchObject({ noShift: true, attempts: 1 })
  })

  it('окончательный отказ — запись НЕ удаляется молча, а помечается failed с причиной', async () => {
    const store = createMemoryStore()
    const item = make('260926-001')
    await store.put(item)
    const send = vi.fn().mockRejectedValue(httpError(409, 'invalid_status'))
    expect(await attemptSend(store, item, send)).toEqual({ kind: 'final', reason: 'closed' })
    expect(await store.list()).toEqual([expect.objectContaining({ id: item.id, failed: 'closed' })])
  })
})

describe('openQueueStore', () => {
  it('без IndexedDB — очередь в памяти (не переживает сеанс)', async () => {
    const store = await openQueueStore(undefined)
    expect(store.persistent).toBe(false)
    await store.put(make('1', 2))
    await store.put(make('2', 1))
    expect((await store.list()).map((i) => i.requestNumber)).toEqual(['2', '1'])
  })

  it('IndexedDB не открылась — тоже память, без исключения', async () => {
    const factory = {
      open: () => {
        const req = {} as IDBOpenDBRequest
        setTimeout(() => (req.onerror as () => void)?.())
        return req
      },
    } as unknown as IDBFactory
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const store = await openQueueStore(factory)
    expect(store.persistent).toBe(false)
    warn.mockRestore()
  })
})
