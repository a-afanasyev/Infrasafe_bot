import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '../../../test/test-utils'
import { memoryQueueWith, queued, TEST_USER_ID } from '../../../test/twaSimple'
import { CompletionQueueProvider, useCompletionQueue } from './CompletionQueue'
import { FOREIGN_TTL_MS } from './policy'
import type { QueueItem, QueueStore } from './types'

// Провайдер очереди: досылка при открытии (по одной, только свои записи),
// автоповтор по расписанию с тем же ключом, окончательный отказ в фоне —
// пометка, а не молчаливое удаление; ждущее смены — только после старта смены.

const { toastMock } = vi.hoisted(() => ({ toastMock: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))
vi.mock('sonner', () => ({ toast: toastMock }))

function Probe() {
  const { items, pendingCount, flushNow } = useCompletionQueue()
  return (
    <div>
      <div data-testid="count">{pendingCount}</div>
      <div data-testid="failed">{items.filter((i) => i.failed).map((i) => `${i.requestNumber}:${i.failed}`).join(',')}</div>
      <button onClick={flushNow}>flush</button>
    </div>
  )
}

function renderQueue(store: QueueStore, send: (item: QueueItem) => Promise<unknown>) {
  return render(
    <CompletionQueueProvider openStore={() => Promise.resolve(store)} send={send} userId={TEST_USER_ID}>
      <Probe />
    </CompletionQueueProvider>,
  )
}

const now = () => ({ nextAttemptAt: Date.now() })

beforeEach(() => Object.values(toastMock).forEach((f) => f.mockReset()))
afterEach(() => vi.useRealTimers())

describe('CompletionQueueProvider', () => {
  it('при открытии досылает свои записи по одной; чужие не шлёт, старые чужие удаляет', async () => {
    const a = queued('260926-001', now())
    const b = queued('260926-002', now())
    const foreignFresh = queued('260926-003', { ...now(), userId: 99 })
    const foreignOld = queued('260926-004', { ...now(), userId: 99, createdAt: Date.now() - FOREIGN_TTL_MS - 1 })
    const store = await memoryQueueWith([a, b, foreignFresh, foreignOld])
    let inFlight = 0
    let maxInFlight = 0
    const send = vi.fn(async () => {
      inFlight += 1
      maxInFlight = Math.max(maxInFlight, inFlight)
      await new Promise((r) => setTimeout(r, 5))
      inFlight -= 1
    })
    renderQueue(store, send)
    await waitFor(() => expect(send).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('0'))
    expect(send.mock.calls.map(([i]) => (i as QueueItem).requestNumber)).toEqual(['260926-001', '260926-002'])
    expect(maxInFlight).toBe(1)
    expect((await store.list()).map((i) => i.requestNumber)).toEqual(['260926-003'])
    expect(toastMock.success).toHaveBeenCalledWith('Фото по заявке 260926-001 отправлено')
  })

  it('сбой — повтор через 5 с с тем же ключом', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const saved = queued('260926-002', now())
    const store = await memoryQueueWith([saved])
    const send = vi.fn().mockRejectedValueOnce({ message: 'Network Error' }).mockResolvedValueOnce({})
    renderQueue(store, send)
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('1'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })
    await waitFor(() => expect(send).toHaveBeenCalledTimes(2))
    expect(send.mock.calls[1][0].idempotencyKey).toBe(saved.idempotencyKey)
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('0'))
  })

  it('окончательный отказ в фоне — запись помечена failed, не удалена, без тоста', async () => {
    const store = await memoryQueueWith([queued('260926-003', now())])
    const send = vi.fn().mockRejectedValue({ response: { status: 502, data: { detail: 'media_rejected' } } })
    renderQueue(store, send)
    await waitFor(() => expect(screen.getByTestId('failed')).toHaveTextContent('260926-003:bad_photo'))
    expect(await store.list()).toHaveLength(1)
    expect(toastMock.error).not.toHaveBeenCalled()
    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('ждущее смены не шлётся при открытии и по таймеру — только после старта смены (flushNow)', async () => {
    const store = await memoryQueueWith([queued('260926-005', { ...now(), noShift: true })])
    const send = vi.fn().mockResolvedValue({})
    renderQueue(store, send)
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('1'))
    await new Promise((r) => setTimeout(r, 30))
    expect(send).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('flush'))
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('0'))
  })
})
