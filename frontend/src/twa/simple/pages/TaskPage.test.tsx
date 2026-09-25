import { describe, it, expect, beforeEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, fireEvent } from '../../../test/test-utils'
import { QueueWrapper, memoryQueueWith } from '../../../test/twaSimple'
import { createQueueItem } from '../queue/engine'
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

async function renderTask(pending = false) {
  const store = await memoryQueueWith(
    pending ? [createQueueItem(NUMBER, new Blob(['x']), 'a.jpg', Date.now() + 60_000)] : [],
  )
  render(
    <QueueWrapper store={store}>
      <Routes>
        <Route path="/twa/s/task/:number" element={<TaskPage />} />
        <Route path="/twa/s/task/:number/done" element={<div>DONE SCREEN</div>} />
      </Routes>
    </QueueWrapper>,
    { routerEntries: [`/twa/s/task/${NUMBER}`] },
  )
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
    await renderTask(true)
    expect(await screen.findByText('Ждёт отправки')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Готово/ })).toBeNull()
  })
})
