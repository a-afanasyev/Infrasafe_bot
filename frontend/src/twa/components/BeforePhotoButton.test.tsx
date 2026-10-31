import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../test/test-utils'
import BeforePhotoButton from './BeforePhotoButton'

// Обычный TWA исполнителя: «Добавить фото до» → сжатие → по одному POST
// /before-photo, у каждого фото свой ключ идемпотентности. Лимит 4 с учётом уже
// загруженных; закрытая заявка — кнопки нет.

const { mockGet, mockPost, mockDownscale, toastMock } = vi.hoisted(() => ({
  mockGet: vi.fn(), mockPost: vi.fn(), mockDownscale: vi.fn(),
  toastMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))
vi.mock('../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost } }))
vi.mock('../utils/downscaleImage', () => ({ downscaleImage: mockDownscale }))
vi.mock('sonner', () => ({ toast: toastMock }))

const N = '260930-001'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
let existing: number

beforeEach(() => {
  existing = 0
  mockGet.mockReset(); mockPost.mockReset(); mockDownscale.mockReset()
  Object.values(toastMock).forEach((f) => f.mockReset())
  mockDownscale.mockImplementation(async (f: File) => f)
  mockGet.mockImplementation(() => Promise.resolve({
    data: Array.from({ length: existing }, (_, i) => ({ id: i + 1, category: 'before_photo', status: 'active' })),
  }))
  mockPost.mockResolvedValue({ data: { media_id: 9, count: 1 } })
})

const pick = (count: number) => {
  const input = screen.getByTestId('before-input') as HTMLInputElement
  const files = Array.from({ length: count }, (_, i) => new File([`b${i}`], `p${i}.jpg`, { type: 'image/jpeg' }))
  fireEvent.change(input, { target: { files } })
}

describe('BeforePhotoButton', () => {
  it('два фото — два POST с разными UUID-ключами, успех — тост', async () => {
    render(<BeforePhotoButton requestNumber={N} status="Закуп" />)
    await screen.findByRole('button', { name: /Добавить фото до/ })
    pick(2)
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(2))
    const keys = mockPost.mock.calls.map(([url, form]) => {
      expect(url).toBe(`/api/v2/requests/${N}/before-photo`)
      return (form as FormData).get('idempotency_key') as string
    })
    keys.forEach((k) => expect(k).toMatch(UUID))
    expect(new Set(keys).size).toBe(2)
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('Фото до загружено: 2'))
  })

  it('3 уже есть, выбрано 2 — уходит только одно (лимит 4)', async () => {
    existing = 3
    render(<BeforePhotoButton requestNumber={N} status="В работе" />)
    await screen.findByText('Фото до: 3 из 4')
    pick(2)
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))
  })

  it('4 уже есть — кнопки нет', async () => {
    existing = 4
    render(<BeforePhotoButton requestNumber={N} status="В работе" />)
    expect(await screen.findByText('Фото до: 4 из 4')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Добавить фото до/ })).toBeNull()
  })

  it('закрытая заявка — ничего не рисует', async () => {
    const { container } = render(<BeforePhotoButton requestNumber={N} status="Выполнена" />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('сбой загрузки — тост ошибки', async () => {
    mockPost.mockRejectedValue({ response: { status: 503, data: { detail: 'media_unavailable' } } })
    render(<BeforePhotoButton requestNumber={N} status="В работе" />)
    await screen.findByRole('button', { name: /Добавить фото до/ })
    pick(1)
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
  })
})
