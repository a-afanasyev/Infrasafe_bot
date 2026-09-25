import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '../../../test/test-utils'
import { memoryQueueWith } from '../../../test/twaSimple'
import { CompletionQueueProvider, useCompletionQueue } from './CompletionQueue'
import { createQueueItem } from './engine'
import type { QueueItem } from './types'

// Провайдер очереди: досылка при открытии приложения, автоповтор по
// расписанию с тем же ключом, окончательный отказ — тост и удаление.

const { toastMock } = vi.hoisted(() => ({ toastMock: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))
vi.mock('sonner', () => ({ toast: toastMock }))

function Count() {
  const { items } = useCompletionQueue()
  return <div data-testid="count">{items.length}</div>
}

const item = (n: string): QueueItem => createQueueItem(n, new Blob(['x'], { type: 'image/jpeg' }), 'a.jpg', Date.now())

beforeEach(() => Object.values(toastMock).forEach((f) => f.mockReset()))
afterEach(() => vi.useRealTimers())

describe('CompletionQueueProvider', () => {
  it('при открытии досылает оставшееся с прошлого раза', async () => {
    const saved = item('260926-001')
    const store = await memoryQueueWith([saved])
    const send = vi.fn().mockResolvedValue({})
    render(
      <CompletionQueueProvider openStore={() => Promise.resolve(store)} send={send}>
        <Count />
      </CompletionQueueProvider>,
    )
    await waitFor(() => expect(send).toHaveBeenCalledWith(expect.objectContaining({ idempotencyKey: saved.idempotencyKey })))
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('0'))
    expect(toastMock.success).toHaveBeenCalledWith('Фото по заявке 260926-001 отправлено')
  })

  it('сбой — повтор через 5 с с тем же ключом', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const saved = item('260926-002')
    const store = await memoryQueueWith([saved])
    const send = vi.fn().mockRejectedValueOnce({ message: 'Network Error' }).mockResolvedValueOnce({})
    render(
      <CompletionQueueProvider openStore={() => Promise.resolve(store)} send={send}>
        <Count />
      </CompletionQueueProvider>,
    )
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('1'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
    })
    await waitFor(() => expect(send).toHaveBeenCalledTimes(2))
    expect(send.mock.calls[1][0].idempotencyKey).toBe(saved.idempotencyKey)
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('0'))
  })

  it('окончательный отказ в фоне — понятный тост, запись убрана', async () => {
    const store = await memoryQueueWith([item('260926-003')])
    const send = vi.fn().mockRejectedValue({ response: { status: 403, data: { detail: 'not_assigned' } } })
    render(
      <CompletionQueueProvider openStore={() => Promise.resolve(store)} send={send}>
        <Count />
      </CompletionQueueProvider>,
    )
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Это не ваша заявка'))
    expect(await store.list()).toEqual([])
  })
})
