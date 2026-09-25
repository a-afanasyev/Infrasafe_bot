import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, fireEvent, waitFor } from '../../../test/test-utils'
import { QueueWrapper, memoryQueueWith, stubTelegram, unstubTelegram } from '../../../test/twaSimple'
import type { QueueStore } from '../queue/types'
import DonePage from './DonePage'

// «Готово»: камера → превью → «Отправить». Фото сначала ложится в очередь,
// затем уходит multipart (photo + idempotency_key). Повтор после сбоя — с
// ТЕМ ЖЕ ключом (сервер примет его как тот же запрос). twaClient шпионим:
// msw + FormData на CI падает (см. CompletionReport.test).

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost, patch: vi.fn() } }))

const NUMBER = '260926-007'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

let store: QueueStore
let status: string

beforeEach(async () => {
  mockPost.mockReset()
  mockGet.mockReset()
  status = 'В работе'
  mockGet.mockImplementation((url: string) =>
    url === `/api/v2/requests/${NUMBER}`
      ? Promise.resolve({ data: { request_number: NUMBER, status, category: 'x', created_at: '2026-09-26T08:00:00Z' } })
      : Promise.reject(new Error(url)),
  )
  store = await memoryQueueWith()
})

afterEach(() => unstubTelegram())

function renderDone() {
  return render(
    <QueueWrapper store={store}>
      <Routes>
        <Route path="/twa/s/task/:number/done" element={<DonePage />} />
        <Route path="/twa/s" element={<div>MINE</div>} />
      </Routes>
    </QueueWrapper>,
    { routerEntries: [`/twa/s/task/${NUMBER}/done`] },
  )
}

async function shootAndSend() {
  const input = (await screen.findByTestId('camera-input')) as HTMLInputElement
  expect(input).toHaveAttribute('accept', 'image/*')
  expect(input).toHaveAttribute('capture', 'environment')
  fireEvent.change(input, { target: { files: [new File(['jpeg-bytes'], 'shot.jpg', { type: 'image/jpeg' })] } })
  fireEvent.click(await screen.findByRole('button', { name: /Отправить/ }))
}

const sentForm = (call: number) => mockPost.mock.calls[call][1] as FormData

describe('DonePage', () => {
  it('отправляет multipart photo + idempotency_key; успех — галка и вибрация success; очередь пуста', async () => {
    const { haptic } = stubTelegram()
    mockPost.mockResolvedValue({ data: {} })
    renderDone()
    await shootAndSend()

    expect(await screen.findByText('Отправлено')).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost.mock.calls[0][0]).toBe(`/api/v2/requests/${NUMBER}/complete`)
    const form = sentForm(0)
    expect((form.get('photo') as File).name).toBe('shot.jpg')
    expect(form.get('idempotency_key')).toMatch(UUID)
    expect(haptic.notificationOccurred).toHaveBeenCalledWith('success')
    expect(await store.list()).toEqual([])
  })

  it('сбой сети — крест, «Ещё раз»; фото в очереди; повтор с тем же ключом', async () => {
    const { haptic } = stubTelegram()
    mockPost.mockRejectedValueOnce({ message: 'Network Error' }).mockResolvedValueOnce({ data: {} })
    renderDone()
    await shootAndSend()

    expect(await screen.findByText('Не отправилось')).toBeInTheDocument()
    expect(screen.getByText('Фото сохранено. Отправим сами')).toBeInTheDocument()
    expect(haptic.notificationOccurred).toHaveBeenCalledWith('error')
    expect(haptic.notificationOccurred).not.toHaveBeenCalledWith('success')
    const [queued] = await store.list()
    expect(queued).toMatchObject({ requestNumber: NUMBER, attempts: 1 })

    fireEvent.click(screen.getByRole('button', { name: /Ещё раз/ }))
    expect(await screen.findByText('Отправлено')).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledTimes(2)
    expect(sentForm(1).get('idempotency_key')).toBe(sentForm(0).get('idempotency_key'))
    expect(sentForm(0).get('idempotency_key')).toBe(queued.idempotencyKey)
    expect(await store.list()).toEqual([])
  })

  it('окончательный отказ (409) — понятный текст, запись убрана из очереди, без «Ещё раз»', async () => {
    stubTelegram()
    mockPost.mockRejectedValue({ response: { status: 409, data: { detail: 'invalid_status' } } })
    renderDone()
    await shootAndSend()

    expect(await screen.findByText('Заявка уже закрыта')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ещё раз/ })).toBeNull()
    expect(screen.queryByText('invalid_status')).toBeNull()
    expect(await store.list()).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: /К моим заявкам/ }))
    expect(await screen.findByText('MINE')).toBeInTheDocument()
  })

  it('заявка не «В работе» (Возвращена) — плашка «Ждёт менеджера», не камера', async () => {
    status = 'Возвращена'
    renderDone()
    expect(await screen.findByText('Ждёт менеджера')).toBeInTheDocument()
    expect(screen.queryByTestId('camera-input')).toBeNull()
    expect(screen.queryByRole('button', { name: /Камера/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /К моим заявкам/ }))
    expect(await screen.findByText('MINE')).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('нет смены (403 no_active_shift) — фото остаётся в очереди, кнопка «Начать смену»', async () => {
    stubTelegram()
    mockPost.mockRejectedValue({ response: { status: 403, data: { detail: 'no_active_shift' } } })
    renderDone()
    await shootAndSend()

    expect(await screen.findByText('Начните смену')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Начать смену/ })).toBeInTheDocument()
    await waitFor(async () => expect(await store.list()).toHaveLength(1))
  })
})
