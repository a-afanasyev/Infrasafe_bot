import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, within, waitFor, fireEvent } from '../../../test/test-utils'
import { QueueWrapper, memoryQueueWith, queued, setOnline } from '../../../test/twaSimple'
import { ConnectionBar } from '../components/Chrome'
import type { QueueItem } from '../queue/types'
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
  { request_number: '260802-005', status: 'Закуп', category: 'repair', address: 'Дом 5', created_at: '2026-08-02T10:00:00Z' },
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

async function renderMine(pendingNumbers: string[] = [], extra: QueueItem[] = []) {
  const store = await memoryQueueWith([...pendingNumbers.map((n) => queued(n)), ...extra])
  // Досылка при открытии не должна успеть закрыть запись в этом тесте.
  mockPost.mockReturnValue(new Promise(() => {}))
  render(
    <QueueWrapper store={store}>
      <ConnectionBar />
      <Routes>
        <Route path="/twa/s" element={<MinePage />} />
        <Route path="/twa/s/task/:number/done" element={<div>DONE SCREEN</div>} />
      </Routes>
    </QueueWrapper>,
    { routerEntries: ['/twa/s'] },
  )
  return store
}

describe('MinePage', () => {
  it('сортирует: вернули → в работе (срочные, по времени) → ждёт менеджера; «ждёт отправки» — в конце', async () => {
    await renderMine(['260801-004'])
    await screen.findByText('Дом 3')
    const tiles = screen.getAllByTestId(/^tile-/).map((el) => el.dataset.testid)
    expect(tiles).toEqual(['tile-260926-003', 'tile-260925-002', 'tile-260901-001', 'tile-260802-005', 'tile-260801-004'])
    // Закуп — не оранжевое «В работе», а серое «Ждёт менеджера».
    expect(within(screen.getByTestId('tile-260802-005')).getByText('Ждёт менеджера')).toBeInTheDocument()
    // Срочная — огонь рядом со статусом.
    expect(within(screen.getByTestId('tile-260925-002')).getByRole('img', { name: 'Срочно' })).toBeInTheDocument()

    const returned = within(screen.getByTestId('tile-260926-003'))
    expect(returned.getByText('Вернули')).toBeInTheDocument()
    expect(returned.getByText('Грязно в подъезде')).toBeInTheDocument()
    expect(within(screen.getByTestId('tile-260901-001')).getByText('Течёт кран')).toBeInTheDocument()
    expect(within(screen.getByTestId('tile-260901-001')).getByText('В работе')).toBeInTheDocument()
    expect(within(screen.getByTestId('tile-260801-004')).getByText('Ждёт отправки')).toBeInTheDocument()
  })

  it('фото отвергнуто в фоне — плитка «Снимите заново», тап ведёт на «Готово»', async () => {
    await renderMine([], [queued('260901-001', { failed: 'bad_photo' })])
    const tile = await screen.findByTestId('tile-260901-001')
    expect(within(tile).getByText('Снимите заново')).toBeInTheDocument()
    fireEvent.click(within(tile).getByRole('button'))
    expect(await screen.findByText('DONE SCREEN')).toBeInTheDocument()
  })

  it('«Готово» отказано окончательно (заявка закрыта) — крупная плашка, «Понятно» убирает запись', async () => {
    const store = await renderMine([], [queued('260920-009', { failed: 'closed', label: 'Дом 9, кв 1' })])
    const lost = await screen.findByTestId('lost-260920-009')
    expect(within(lost).getByText('Заявка уже закрыта')).toBeInTheDocument()
    expect(within(lost).getByText('Дом 9, кв 1')).toBeInTheDocument()
    fireEvent.click(within(lost).getByRole('button', { name: /Понятно/ }))
    await waitFor(() => expect(screen.queryByTestId('lost-260920-009')).toBeNull())
    expect(await store.list()).toEqual([])
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
