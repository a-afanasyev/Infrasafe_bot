import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import type { CleaningMyTasks } from './api'
import CleaningPage from './CleaningPage'
import CleaningEntry from './CleaningEntry'
import { type CleaningQueueItem, type SendResult, createMemoryStore } from './queue'

const TASKS: CleaningMyTasks = {
  work_date: '2026-11-17',
  day_end_at: '2026-11-17T17:00:00Z',
  tasks: [{
    id: 7, building_id: 1, address: 'д. 12', entrance: 3, works: ['wet', 'elevator'], status: 'in_progress',
    version: 2, session_open: false,
    slots: [
      { slot: 'floor:6', done: true, photo_id: 41, captured_at: '2026-11-17T06:00:00Z' },
      { slot: 'floor:7', done: false, photo_id: null, captured_at: null },
      { slot: 'point:elevator', done: false, photo_id: null, captured_at: null },
    ],
  }],
}

let sessions = 0

beforeEach(() => {
  sessions = 0
  server.use(
    http.get('*/api/v2/cleaning/my/tasks', () => HttpResponse.json(TASKS)),
    http.get('*/api/v2/profile', () => HttpResponse.json({ id: 11 })),
    http.post('*/api/v2/cleaning/tasks/7/session', () => {
      sessions += 1
      return new HttpResponse(null, { status: 204 })
    }),
  )
})

describe('CleaningPage', () => {
  it('показывает подъезд с прогрессом, открывает сессию и ставит кадр этажа в очередь', async () => {
    const store = createMemoryStore()
    const sent: CleaningQueueItem[] = []
    const send = vi.fn(async (item: CleaningQueueItem): Promise<SendResult> => {
      sent.push(item)
      return { kind: 'retry' } // связи нет — кадр остаётся в очереди
    })
    const user = userEvent.setup()
    render(<CleaningPage backTo="/twa/s/shift" openStore={async () => store} send={send} />)

    await user.click(await screen.findByRole('button', { name: /д\. 12 · подъезд 3/ }))
    await waitFor(() => expect(sessions).toBe(1))
    expect(screen.getByTestId('cleaning-progress')).toHaveTextContent('снято 1 из 3')
    expect(screen.getByRole('button', { name: 'Этаж 6: снято' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Лифт: снять' })).toBeInTheDocument()

    // В jsdom живой камеры нет — страница честно уходит на системную.
    await user.click(screen.getByRole('button', { name: 'Этаж 7: снять' }))
    const input = (await screen.findByText('Открыть камеру')).querySelector('input') as HTMLInputElement
    await user.upload(input, new File(['frame'], 'shot.jpg', { type: 'image/jpeg' }))

    await waitFor(() => expect(send).toHaveBeenCalled())
    expect([sent[0].taskId, sent[0].slot, sent[0].source, sent[0].userId]).toEqual([7, 'floor:7', 'system', 11])
    expect(await screen.findByRole('button', { name: 'Этаж 7: ждёт связи' })).toBeInTheDocument()
    expect(screen.getByTestId('cleaning-progress')).toHaveTextContent('снято 2 из 3')
    expect((await store.list()).map((i) => i.slot)).toEqual(['floor:7'])
  })

  it('окончательный отказ виден на кнопке точки', async () => {
    const store = createMemoryStore()
    await store.put({
      id: 'x', userId: 11, taskId: 7, slot: 'point:elevator', photo: new Blob(['x']), capturedAt: 1, source: 'live',
      attempts: 0, nextAttemptAt: 0, failed: 'frozen',
    })
    const user = userEvent.setup()
    render(<CleaningPage backTo="/twa/s/shift" openStore={async () => store} send={async () => ({ kind: 'done' })} />)
    await user.click(await screen.findByRole('button', { name: /д\. 12 · подъезд 3/ }))
    const button = await screen.findByRole('button', { name: 'Лифт: не принято' })
    expect(button).toHaveTextContent('задание уже закрыто')
  })
})

describe('CleaningEntry', () => {
  it('при выключенном модуле не шлёт запрос вовсе', async () => {
    let hits = 0
    server.use(http.get('*/api/v2/cleaning/my/tasks', () => { hits += 1; return new HttpResponse(null, { status: 404 }) }))
    const { container } = render(<CleaningEntry to="/twa/s/cleaning" />)
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(container).toBeEmptyDOMElement()
    expect(hits).toBe(0)
  })

  it('виден уборщице с заданиями и пуст для остальных', async () => {
    vi.stubEnv('VITE_CLEANING_ENABLED', 'true')
    const { unmount } = render(<CleaningEntry to="/twa/s/cleaning" />)
    expect(await screen.findByTestId('cleaning-entry')).toHaveTextContent('осталось подъездов: 1 из 1')
    unmount()

    server.use(http.get('*/api/v2/cleaning/my/tasks', () => new HttpResponse(null, { status: 403 })))
    const { container } = render(<CleaningEntry to="/twa/s/cleaning" />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
    vi.unstubAllEnvs()
  })
})
