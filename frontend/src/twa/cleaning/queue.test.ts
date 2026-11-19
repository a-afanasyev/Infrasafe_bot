import { describe, expect, it } from 'vitest'
import { type CleaningQueueItem, type SendResult, createMemoryStore, enqueue, flush } from './queue'

const item = (over: Partial<CleaningQueueItem> = {}): CleaningQueueItem => ({
  id: crypto.randomUUID(), userId: 1, taskId: 7, slot: 'floor:1', photo: new Blob(['x'], { type: 'image/jpeg' }),
  capturedAt: 1000, source: 'live', attempts: 0, nextAttemptAt: 0, ...over,
})

describe('cleaning queue', () => {
  it('пересъёмка заменяет неотправленный кадр той же точки, чужие точки не трогает', async () => {
    const store = createMemoryStore()
    await enqueue(store, item({ id: 'a' }))
    await enqueue(store, item({ id: 'b', slot: 'floor:2', capturedAt: 1500 }))
    await enqueue(store, item({ id: 'c', capturedAt: 2000 }))
    expect((await store.list()).map((i) => i.id)).toEqual(['b', 'c'])
  })

  it('отправленное удаляется, окончательный отказ остаётся на точке и больше не шлётся', async () => {
    const store = createMemoryStore()
    await enqueue(store, item({ id: 'ok' }))
    await enqueue(store, item({ id: 'bad', slot: 'floor:2', capturedAt: 1100 }))
    const calls: string[] = []
    const send = async (i: CleaningQueueItem): Promise<SendResult> => {
      calls.push(i.id)
      return i.id === 'bad' ? { kind: 'final', reason: 'frozen' } : { kind: 'done' }
    }
    expect(await flush(store, send, 1)).toBe(1)
    expect(await flush(store, send, 1)).toBe(0)
    const left = await store.list()
    expect(left.map((i) => [i.id, i.failed])).toEqual([['bad', 'frozen']])
    expect(calls).toEqual(['ok', 'bad'])
  })

  it('без связи запись откладывается с тем же ключом, а очередь не долбит сервер дальше', async () => {
    const store = createMemoryStore()
    await enqueue(store, item({ id: 'a' }))
    await enqueue(store, item({ id: 'b', slot: 'floor:2', capturedAt: 1100 }))
    let now = 10_000
    const calls: string[] = []
    const offline = async (i: CleaningQueueItem): Promise<SendResult> => {
      calls.push(i.id)
      throw new Error('network')
    }
    expect(await flush(store, offline, 1, () => now)).toBe(0)
    expect(calls).toEqual(['a']) // вторую не пробуем — связи нет
    const [first] = await store.list()
    expect([first.id, first.attempts]).toEqual(['a', 1])
    expect(first.nextAttemptAt).toBeGreaterThan(now)

    expect(await flush(store, offline, 1, () => now)).toBe(0) // срок повтора не подошёл: «a» ждёт, пробуем «b»
    now = first.nextAttemptAt + 200_000
    const online = async (): Promise<SendResult> => ({ kind: 'done' })
    expect(await flush(store, online, 1, () => now)).toBe(2)
    expect(await store.list()).toEqual([])
  })

  it('на общем телефоне чужие записи не отправляются', async () => {
    const store = createMemoryStore()
    await enqueue(store, item({ id: 'mine' }))
    await enqueue(store, item({ id: 'other', userId: 2, slot: 'floor:2' }))
    expect(await flush(store, async () => ({ kind: 'done' }), 1)).toBe(1)
    expect((await store.list()).map((i) => i.id)).toEqual(['other'])
  })
})
