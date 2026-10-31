import { describe, it, expect, beforeEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, fireEvent, waitFor } from '../../../test/test-utils'
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
        <Route path="/twa/s/task/:number/before" element={<div>BEFORE SCREEN</div>} />
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

describe('simple TaskPage — фото «до»', () => {
  const media = (items: Array<{ id: number; category: string }>) => {
    mockGet.mockImplementation((url: string) => {
      if (url === `/api/v2/requests/${NUMBER}`) return Promise.resolve({ data: request })
      if (url === `/api/v2/media/request/${NUMBER}`)
        return Promise.resolve({ data: items.map((i) => ({ ...i, file_type: 'photo', status: 'active' })) })
      return Promise.reject(new Error(url))
    })
  }

  it('«Закуп»: «Фото до» есть и ведёт на камеру «до»; «Готово» — нет (ждёт менеджера)', async () => {
    request = { ...request, status: 'Закуп', return_reason: null }
    await renderTask()
    fireEvent.click(await screen.findByRole('button', { name: /Фото до/ }))
    expect(await screen.findByText('BEFORE SCREEN')).toBeInTheDocument()
  })

  it('«Фото до» ждёт отправки — «Готово» доступно, плашки «Ждёт отправки» нет', async () => {
    request = { ...request, status: 'В работе', return_reason: null }
    await renderTask([queued(NUMBER, { kind: 'before' })])
    expect(await screen.findByRole('button', { name: /Готово/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Проблема/ })).toBeInTheDocument()
    expect(screen.queryByText('Ждёт отправки')).toBeNull()
    expect(screen.getByText('Фото «до» ждёт отправки: 1')).toBeInTheDocument()
  })

  it('уже 4 фото «до» — кнопки нет, миниатюры есть; фото «до» не выдаётся за фото жителя', async () => {
    request = { ...request, status: 'В работе', return_reason: null }
    media([1, 2, 3, 4].map((id) => ({ id, category: 'before_photo' })))
    await renderTask()
    expect(await screen.findAllByTestId('before-thumb')).toHaveLength(4)
    expect(screen.queryByRole('button', { name: /Фото до/ })).toBeNull()
    expect(screen.queryByAltText('Фото жителя')).toBeNull()
  })

  it('3 фото + 1 в очереди = лимит: кнопки нет', async () => {
    request = { ...request, status: 'В работе', return_reason: null }
    media([1, 2, 3].map((id) => ({ id, category: 'before_photo' })))
    await renderTask([queued(NUMBER, { kind: 'before' })])
    expect(await screen.findAllByTestId('before-thumb')).toHaveLength(3)
    expect(screen.queryByRole('button', { name: /Фото до/ })).toBeNull()
  })

  it('закрытая заявка — «Фото до» нет', async () => {
    request = { ...request, status: 'Выполнена' }
    await renderTask()
    expect(await screen.findByText('Заявка закрыта')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Фото до/ })).toBeNull()
  })

  it('проваленное «до» — плашка у фото, не полноэкранный исход; «Убрать» удаляет запись', async () => {
    request = { ...request, status: 'В работе', return_reason: null }
    const store = await renderTask([queued(NUMBER, { kind: 'before', failed: 'bad_photo' })])
    expect(await screen.findByText('Фото «до» не отправлено: Фото не подошло. Снимите заново')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Готово/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Убрать/ }))
    await waitFor(async () => expect(await store.list()).toEqual([]))
  })
})
