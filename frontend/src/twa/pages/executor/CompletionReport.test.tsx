import { describe, it, expect, beforeEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, waitFor, fireEvent } from '../../../test/test-utils'
import CompletionReport from './CompletionReport'
import { MAX_REQUEST_TEXT_LENGTH } from '../../../constants'

// TEST-068: отчёт о выполнении — PATCH «Выполнена» с текстом отчёта, затем
// фото под category=completion_photo (сбой фото не откатывает статус),
// после успеха — на список задач.

const { mockPost, mockPatch, toastMock } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  toastMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))
vi.mock('../../twaClient', () => ({ twaClient: { post: mockPost, patch: mockPatch, get: vi.fn() } }))
vi.mock('sonner', () => ({ toast: toastMock }))

const NUMBER = '260918-003'

function renderPage() {
  return render(
    <Routes>
      <Route path="/twa/exec/report/:number" element={<CompletionReport />} />
      <Route path="/twa/exec" element={<div>TASK LIST</div>} />
    </Routes>,
    { routerEntries: [`/twa/exec/report/${NUMBER}`] },
  )
}

function addPhotos(container: HTMLElement, names: string[]) {
  const gallery = container.querySelectorAll('input[type="file"]')[1] as HTMLInputElement
  fireEvent.change(gallery, { target: { files: names.map((n) => new File(['x'], n, { type: 'image/jpeg' })) } })
}

beforeEach(() => {
  mockPost.mockReset()
  mockPatch.mockReset()
  toastMock.error.mockReset()
  toastMock.warning.mockReset()
  mockPatch.mockResolvedValue({ data: { ok: true } })
  mockPost.mockImplementation((_url: string, body: FormData) => {
    const f = body.get('file') as File
    return f.name === 'bad.jpg' ? Promise.reject(new Error('413')) : Promise.resolve({ data: {} })
  })
})

describe('CompletionReport', () => {
  it('без текста и фото: PATCH без completion_report → переход на список задач', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Отметить выполненной' }))
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(`/api/v2/requests/${NUMBER}`, { status: 'Выполнена', completion_report: undefined }))
    expect(await screen.findByText('TASK LIST')).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('текст отчёта и фото: PATCH с отчётом, фото под completion_photo, сбой одного — warning', async () => {
    const { container } = renderPage()
    fireEvent.change(await screen.findByPlaceholderText('Что было сделано...'), { target: { value: 'Заменил кран' } })
    addPhotos(container, ['ok.jpg', 'bad.jpg'])
    fireEvent.click(screen.getByRole('button', { name: 'Отметить выполненной' }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(`/api/v2/requests/${NUMBER}`, { status: 'Выполнена', completion_report: 'Заменил кран' }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(2))
    const form = mockPost.mock.calls[0][1] as FormData
    expect(form.get('request_number')).toBe(NUMBER)
    expect(form.get('category')).toBe('completion_photo')
    await waitFor(() => expect(toastMock.warning).toHaveBeenCalledWith('Заявка завершена, но не загрузились фото №2'))
    expect(await screen.findByText('TASK LIST')).toBeInTheDocument()
  })

  it('ошибка PATCH → toast.error, остаёмся на форме', async () => {
    mockPatch.mockRejectedValue({ response: { status: 422, data: { detail: 'Переход запрещён' } } })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Отметить выполненной' }))
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
    expect(screen.getByText('Отчёт о выполнении')).toBeInTheDocument()
    expect(screen.queryByText('TASK LIST')).toBeNull()
  })

  it('поле отчёта ограничено лимитом API (MAX_REQUEST_TEXT_LENGTH = 2000)', async () => {
    renderPage()
    const field = await screen.findByPlaceholderText('Что было сделано...')
    expect(MAX_REQUEST_TEXT_LENGTH).toBe(2000)
    expect(field).toHaveAttribute('maxLength', '2000')
  })
})
