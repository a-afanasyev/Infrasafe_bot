import { describe, it, expect, beforeEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, fireEvent } from '../../../test/test-utils'
import { QueueWrapper, memoryQueueWith, queued } from '../../../test/twaSimple'
import type { QueueItem } from '../queue/types'
import TaskPage from './TaskPage'

// Карточка заявки простого режима: адрес, весь текст, «Вернули: причина»,
// номер мелко; «Готово» / «Проблема». Пока «Готово» в очереди — кнопок нет.

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost, patch: vi.fn() } }))

const NUMBER = '260926-010'
let request: Record<string, unknown>

beforeEach(() => {
  request = {
    request_number: NUMBER,
    status: 'Возвращена',
    category: 'plumbing',
    address: 'Дом 5, кв 45',
    description: 'Течёт кран\nна кухне',
    return_reason: 'Всё ещё капает',
    created_at: '2026-09-26T08:00:00Z',
  }
  mockGet.mockReset()
  mockPost.mockReset()
  mockPost.mockReturnValue(new Promise(() => {}))
  mockGet.mockImplementation((url: string) => {
    if (url === `/api/v2/requests/${NUMBER}`) return Promise.resolve({ data: request })
    if (url === `/api/v2/media/request/${NUMBER}`) return Promise.resolve({ data: [] })
    return Promise.reject(new Error(url))
  })
})

async function renderTask(items: QueueItem[] = []) {
  const store = await memoryQueueWith(items)
  render(
    <QueueWrapper store={store}>
      <Routes>
        <Route path="/twa/s/task/:number" element={<TaskPage />} />
        <Route path="/twa/s/task/:number/done" element={<div>DONE SCREEN</div>} />
        <Route path="/twa/s" element={<div>MINE</div>} />
      </Routes>
    </QueueWrapper>,
    { routerEntries: [`/twa/s/task/${NUMBER}`] },
  )
  return store
}

describe('simple TaskPage', () => {
  it('«Возвращена»: адрес, текст, «Вернули: причина», номер; вместо «Готово» — «Ждёт менеджера», «Проблема» есть', async () => {
    await renderTask()
    expect(await screen.findByRole('heading', { name: 'Дом 5, кв 45' })).toBeInTheDocument()
    expect(screen.getByText('Вернули: Всё ещё капает')).toBeInTheDocument()
    expect(screen.getByText(/Течёт кран/)).toBeInTheDocument()
    expect(screen.getByText(`№ ${NUMBER}`)).toBeInTheDocument()
    expect(screen.getByText('Ждёт менеджера')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Готово/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Проблема/ })).toBeInTheDocument()
  })

  it('«В работе»: «Готово» → экран «Готово»', async () => {
    request = { ...request, status: 'В работе', return_reason: null }
    await renderTask()
    fireEvent.click(await screen.findByRole('button', { name: /Готово/ }))
    expect(await screen.findByText('DONE SCREEN')).toBeInTheDocument()
  })

  it('«Готово» уже в очереди — «Ждёт отправки», без кнопок', async () => {
    await renderTask([queued(NUMBER)])
    expect(await screen.findByText('Ждёт отправки')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Готово/ })).toBeNull()
  })

  it('закрытая (отменена) — плашка «Заявка закрыта», без кнопок', async () => {
    request = { ...request, status: 'Отменена' }
    await renderTask()
    expect(await screen.findByText('Заявка закрыта')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Готово|Проблема/ })).toBeNull()
    expect(screen.queryByText('Ждёт менеджера')).toBeNull()
  })

  it('фоновый «Готово» отказан (не ваша) — исход на весь экран, «Понятно» убирает запись', async () => {
    request = { ...request, status: 'В работе' }
    const store = await renderTask([queued(NUMBER, { failed: 'not_yours' })])
    expect(await screen.findByRole('alert')).toHaveTextContent('Это не ваша заявка')
    fireEvent.click(screen.getByRole('button', { name: /Понятно/ }))
    expect(await screen.findByText('MINE')).toBeInTheDocument()
    expect(await store.list()).toEqual([])
  })

  it('фото отвергнуто — вместо «Готово» крупное «Снимите заново»', async () => {
    request = { ...request, status: 'В работе' }
    await renderTask([queued(NUMBER, { failed: 'bad_photo' })])
    fireEvent.click(await screen.findByRole('button', { name: /Снимите заново/ }))
    expect(await screen.findByText('DONE SCREEN')).toBeInTheDocument()
  })
})
