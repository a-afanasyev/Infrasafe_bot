import { describe, it, expect, beforeEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import userEvent from '@testing-library/user-event'
import { render, screen, waitFor, fireEvent } from '../../../test/test-utils'
import TaskDetailPage from './TaskDetailPage'

// TEST-068: карточка задачи исполнителя в TWA. Кнопки действий зависят от
// статуса; «Новая» берётся через POST /claim (EXECUTOR_CLAIM), «Выполнена»
// уводит на страницу отчёта, «Закуп» сначала открывает шторку с текстом.
// Галерея (MediaGallery) грузит байты как blob → data: URL и открывает лайтбокс.

const { mockGet, mockPost, mockPatch, toastMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  toastMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost, patch: mockPatch } }))
vi.mock('sonner', () => ({ toast: toastMock }))

const NUMBER = '260918-001'

function request(overrides: Record<string, unknown> = {}) {
  return {
    request_number: NUMBER,
    status: 'Новая',
    category: 'electricity',
    description: 'Не горит свет в подъезде',
    address: 'ул. Ленина, 1',
    created_at: '2026-09-18T08:00:00Z',
    requested_materials: null,
    notes: null,
    completion_report: null,
    ...overrides,
  }
}

const MEDIA = [
  { id: 101, file_type: 'photo', mime_type: 'image/jpeg', category: null },
  { id: 102, file_type: 'video', mime_type: 'video/mp4', category: null },
  { id: 103, file_type: 'photo', mime_type: 'image/jpeg', category: 'completion_photo' },
]

let requestState: Record<string, unknown>
let failingFileIds: number[]

function mockApi(media: unknown[] = MEDIA) {
  mockGet.mockImplementation((url: string) => {
    if (url === `/api/v2/requests/${NUMBER}`) return Promise.resolve({ data: requestState })
    if (url === `/api/v2/media/request/${NUMBER}`) return Promise.resolve({ data: media })
    const m = /\/api\/v2\/media\/(\d+)\/file/.exec(url)
    if (m) {
      return failingFileIds.includes(Number(m[1]))
        ? Promise.reject(new Error('404'))
        : Promise.resolve({ data: new Blob(['img'], { type: 'image/jpeg' }) })
    }
    if (url === `/api/v2/requests/${NUMBER}/comments`) return Promise.resolve({ data: [] })
    if (url === '/api/v2/profile') return Promise.resolve({ data: { id: 1, roles: ['executor'] } })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
  mockPatch.mockImplementation((_url: string, body: { status: string }) => {
    requestState = { ...requestState, status: body.status }
    return Promise.resolve({ data: requestState })
  })
  mockPost.mockImplementation((url: string) => {
    if (url === `/api/v2/requests/${NUMBER}/claim`) {
      requestState = { ...requestState, status: 'В работе' }
      return Promise.resolve({ data: requestState })
    }
    return Promise.resolve({ data: { id: 1 } })
  })
}

function renderPage() {
  return render(
    <Routes>
      <Route path="/twa/exec/task/:number" element={<TaskDetailPage />} />
      <Route path="/twa/exec/report/:number" element={<div>REPORT PAGE</div>} />
    </Routes>,
    { routerEntries: [`/twa/exec/task/${NUMBER}`] },
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPatch.mockReset()
  toastMock.error.mockReset()
  requestState = request()
  failingFileIds = []
  mockApi()
})

describe('TaskDetailPage — карточка и действия', () => {
  it('рендерит заявку: номер, категория, описание, адрес, блоки материалов/уточнения/отчёта', async () => {
    requestState = request({
      status: 'Выполнена',
      requested_materials: 'Лампы 3 шт',
      notes: 'Какой подъезд?',
      completion_report: 'Заменил лампы',
    })
    renderPage()
    expect(await screen.findByText(NUMBER)).toBeInTheDocument()
    expect(screen.getByText('Электрика')).toBeInTheDocument()
    expect(screen.getByText('Не горит свет в подъезде')).toBeInTheDocument()
    expect(screen.getByText('ул. Ленина, 1')).toBeInTheDocument()
    expect(screen.getByText('Лампы 3 шт')).toBeInTheDocument()
    expect(screen.getByText('Какой подъезд?')).toBeInTheDocument()
    expect(screen.getByText('Заменил лампы')).toBeInTheDocument()
    // «Выполнена»: у исполнителя действий нет (reopen — менеджерский).
    expect(screen.queryByRole('button', { name: 'В работу' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Выполнена' })).toBeNull()
  })

  it('«Новая» → «В работу» берёт заявку через POST /claim (не PATCH статуса) и перерисовывает действия', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'В работу' }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(`/api/v2/requests/${NUMBER}/claim`))
    expect(mockPatch).not.toHaveBeenCalled()
    // После инвалидации заявка перечитана — появились действия «В работе».
    expect(await screen.findByRole('button', { name: 'Закуп' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Выполнена' })).toBeInTheDocument()
  })

  it('взятие: 409 already_claimed → локализованный тост «уже взял другой»', async () => {
    mockPost.mockRejectedValue({ response: { status: 409, data: { detail: 'already_claimed' } } })
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'В работу' }))
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Заявку уже взял другой исполнитель'))
  })

  it('взятие: 403 not_eligible → локализованный тост про смену/специализацию', async () => {
    mockPost.mockRejectedValue({ response: { status: 403, data: { detail: 'not_eligible' } } })
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'В работу' }))
    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith('Нельзя взять заявку: вы не на смене или она не для вашей специализации'),
    )
  })

  it('«В работе»: у исполнителя нет «Уточнения» (переход только у менеджера)', async () => {
    requestState = request({ status: 'В работе' })
    renderPage()
    expect(await screen.findByRole('button', { name: 'Закуп' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Уточнение' })).toBeNull()
  })

  it('«Уточнение» (поставил менеджер) → «В работу» шлёт PATCH status=«В работе»', async () => {
    requestState = request({ status: 'Уточнение' })
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'В работу' }))
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(`/api/v2/requests/${NUMBER}`, { status: 'В работе' }))
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('«Выполнена» уводит на страницу отчёта, а не меняет статус', async () => {
    requestState = request({ status: 'В работе' })
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Выполнена' }))
    expect(await screen.findByText('REPORT PAGE')).toBeInTheDocument()
    expect(mockPatch).not.toHaveBeenCalled()
  })

  it('«Закуп»: шторка, подтверждение заблокировано без текста, PATCH с requested_materials', async () => {
    requestState = request({ status: 'В работе' })
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Закуп' }))
    expect(screen.getByText('Что нужно закупить?')).toBeInTheDocument()
    const confirm = screen.getByRole('button', { name: 'Подтвердить' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByPlaceholderText('Список материалов...'), 'Кабель 10 м')
    expect(confirm).toBeEnabled()
    await user.click(confirm)
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith(`/api/v2/requests/${NUMBER}`, { status: 'Закуп', requested_materials: 'Кабель 10 м' }),
    )
    await waitFor(() => expect(screen.queryByText('Что нужно закупить?')).toBeNull())
    // Из «Закуп» доступен только возврат в работу.
    expect(await screen.findByRole('button', { name: 'В работу' })).toBeInTheDocument()
  })

  it('ошибка смены статуса → toast.error с нашим текстом (не сырой detail бэкенда), статус не меняется', async () => {
    requestState = request({ status: 'Закуп' })
    mockPatch.mockRejectedValue({ response: { status: 422, data: { detail: 'Переход запрещён' } } })
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'В работу' }))
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Не удалось изменить статус'))
    expect(toastMock.error).not.toHaveBeenCalledWith('Переход запрещён')
    expect(screen.getByRole('button', { name: 'В работу' })).toBeInTheDocument()
  })

  it('заявка не найдена → «Ошибка»', async () => {
    mockGet.mockImplementation((url: string) =>
      url === `/api/v2/requests/${NUMBER}` ? Promise.resolve({ data: null }) : Promise.resolve({ data: [] }),
    )
    renderPage()
    expect(await screen.findByText('Ошибка')).toBeInTheDocument()
  })
})

describe('TaskDetailPage — галерея (MediaGallery)', () => {
  it('фото заявки и фотоотчёт в разных секциях; байты → data: URL; видео помечено', async () => {
    requestState = request({ status: 'Выполнена' })
    renderPage()
    expect(await screen.findByText('Фото')).toBeInTheDocument()
    expect(screen.getByText('Фотоотчёт')).toBeInTheDocument()
    await waitFor(() => expect(document.querySelectorAll('img[src^="data:image/jpeg"]')).toHaveLength(3))
    expect(screen.getByText('▶')).toBeInTheDocument()
    const fileCalls = mockGet.mock.calls.filter(([u]) => String(u).includes('/file'))
    expect(fileCalls).toHaveLength(3)
    expect(fileCalls[0][1]).toEqual({ responseType: 'blob' })
  })

  it('тап по миниатюре открывает лайтбокс; Escape и крестик закрывают', async () => {
    renderPage()
    await waitFor(() => expect(document.querySelectorAll('img[src^="data:"]').length).toBeGreaterThan(0))
    const thumbs = screen.getAllByRole('button').filter((b) => b.querySelector('img'))
    fireEvent.click(thumbs[0])
    // Лайтбокс: своя загрузка полного файла → ещё один img.
    await waitFor(() => expect(document.querySelectorAll('.fixed.inset-0 img')).toHaveLength(1))
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(document.querySelector('.fixed.inset-0')).toBeNull())

    fireEvent.click(thumbs[0])
    await waitFor(() => expect(document.querySelector('.fixed.inset-0')).not.toBeNull())
    fireEvent.click(document.querySelector('.fixed.inset-0 > button') as HTMLElement)
    await waitFor(() => expect(document.querySelector('.fixed.inset-0')).toBeNull())
  })

  it('сбой загрузки байтов: плитка-заглушка вместо кнопки, лайтбокс сообщает об ошибке', async () => {
    failingFileIds = [102]
    renderPage()
    await waitFor(() => expect(document.querySelectorAll('img[src^="data:"]')).toHaveLength(2))
    // Плитка 102 — не кнопка (ImageOff), кнопок с картинкой две.
    expect(screen.getAllByRole('button').filter((b) => b.querySelector('img'))).toHaveLength(2)

    // Лайтбокс на 101 падает, если файл перестал отдаваться.
    failingFileIds = [101, 102]
    const thumb = screen.getAllByRole('button').filter((b) => b.querySelector('img'))[0]
    fireEvent.click(thumb)
    expect(await screen.findByText('Не удалось загрузить')).toBeInTheDocument()
  })

  it('без подходящих медиа секция с заголовком не рендерится вовсе', async () => {
    mockApi([{ id: 103, file_type: 'photo', mime_type: 'image/jpeg', category: 'completion_photo' }])
    renderPage()
    expect(await screen.findByText('Фотоотчёт')).toBeInTheDocument()
    expect(screen.queryByText('Фото')).toBeNull()
  })
})
