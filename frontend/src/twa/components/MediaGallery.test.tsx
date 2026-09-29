import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '../../test/test-utils'
import MediaGallery from './MediaGallery'

// Ревью медиасервиса 2026-09-28: сбой media-service прокси больше не маскирует
// пустым списком — галерея обязана показать ошибку, а не «фото нет».

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))
vi.mock('../twaClient', () => ({ twaClient: { get: mockGet } }))

afterEach(() => mockGet.mockReset())

describe('MediaGallery', () => {
  it('ошибка списка медиа видна пользователю', async () => {
    mockGet.mockRejectedValue(Object.assign(new Error('502'), { response: { status: 502 } }))
    render(<MediaGallery requestNumber="260928-001" kind="request" />)
    expect(await screen.findByText('Не удалось загрузить фото — попробуйте позже')).toBeInTheDocument()
  })

  it('пустой список — ничего не рисует', async () => {
    mockGet.mockResolvedValue({ data: [] })
    const { container } = render(<MediaGallery requestNumber="260928-001" kind="request" title="Фото" />)
    await vi.waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(container.textContent).not.toContain('Не удалось')
  })
})
