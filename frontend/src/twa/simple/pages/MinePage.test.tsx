import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, within, waitFor } from '../../../test/test-utils'
import { QueueWrapper, memoryQueueWith, setOnline } from '../../../test/twaSimple'
import { ConnectionBar } from '../components/Chrome'
import { createQueueItem } from '../queue/engine'
import MinePage from './MinePage'

// «Мои» простого режима: вернули → срочные → по времени; «ждёт отправки» —
// из локальной очереди; ошибка загрузки — «Ещё раз», а не «Всё сделано».

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost, patch: vi.fn() } }))

const TASKS = [
  { request_number: '260901-001', status: 'В работе', category: 'plumbing', address: 'Дом 1, кв 1', description: 'Течёт кран\nподробности', created_at: '2026-09-01T10:00:00Z' },
  { request_number: '260925-002', status: 'В работе', category: 'electricity', urgency: 'high', address: 'Дом 2, кв 2', created_at: '2026-09-25T10:00:00Z' },
  { request_number: '260926-003', status: 'Возвращена', category: 'cleaning', return_reason: 'Грязно в подъезде', address: 'Дом 3', created_at: '2026-09-26T10:00:00Z' },
  { request_number: '260801-004', status: 'В работе', category: 'repair', address: 'Дом 4', created_at: '2026-08-01T10:00:00Z' },
]

let tasks: unknown = TASKS

beforeEach(() => {
  tasks = TASKS
  mockGet.mockReset()
  mockGet.mockImplementation((url: string) => {
    if (url === '/api/v2/requests') return tasks instanceof Error ? Promise.reject(tasks) : Promise.resolve({ data: tasks })
    if (url.startsWith('/api/v2/media/request/')) return Promise.resolve({ data: [] })
    if (url === '/api/v2/executor/shifts/current') return Promise.resolve({ data: null })
    return Promise.reject(new Error(url))
  })
})

afterEach(() => setOnline(true))

async function renderMine(pendingNumbers: string[] = []) {
  const store = await memoryQueueWith(
    pendingNumbers.map((n, i) => createQueueItem(n, new Blob(['x']), 'a.jpg', Date.now() + 60_000 + i)),
  )
  // Досылка при открытии не должна успеть закрыть запись в этом тесте.
  mockPost.mockReturnValue(new Promise(() => {}))
  return render(
    <QueueWrapper store={store}>
      <ConnectionBar />
      <MinePage />
    </QueueWrapper>,
    { routerEntries: ['/twa/s'] },
  )
}

describe('MinePage', () => {
  it('сортирует: вернули (с причиной) → срочные → по времени; «ждёт отправки» — в конце', async () => {
    await renderMine(['260801-004'])
    await screen.findByText('Дом 3')
    const tiles = screen.getAllByTestId(/^tile-/).map((el) => el.dataset.testid)
    expect(tiles).toEqual(['tile-260926-003', 'tile-260925-002', 'tile-260901-001', 'tile-260801-004'])

    const returned = within(screen.getByTestId('tile-260926-003'))
    expect(returned.getByText('Вернули')).toBeInTheDocument()
    expect(returned.getByText('Грязно в подъезде')).toBeInTheDocument()
    expect(within(screen.getByTestId('tile-260901-001')).getByText('Течёт кран')).toBeInTheDocument()
    expect(within(screen.getByTestId('tile-260901-001')).getByText('В работе')).toBeInTheDocument()
    expect(within(screen.getByTestId('tile-260801-004')).getByText('Ждёт отправки')).toBeInTheDocument()
  })

  it('пусто — «Всё сделано»', async () => {
    tasks = []
    await renderMine()
    expect(await screen.findByText('Всё сделано')).toBeInTheDocument()
  })

  it('ошибка загрузки — знак и «Ещё раз», не «Всё сделано»', async () => {
    tasks = new Error('Network Error')
    await renderMine()
    expect(await screen.findByText('Не загрузилось')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Ещё раз/ })).toBeInTheDocument()
    expect(screen.queryByText('Всё сделано')).toBeNull()
  })

  it('нет связи — жёлтая полоса «Нет связи» и «Фото ждёт: N»', async () => {
    setOnline(false)
    await renderMine(['260901-001'])
    await waitFor(() => expect(screen.getByText('Фото ждёт: 1')).toBeInTheDocument())
    expect(screen.getByText('Нет связи')).toBeInTheDocument()
  })
})
