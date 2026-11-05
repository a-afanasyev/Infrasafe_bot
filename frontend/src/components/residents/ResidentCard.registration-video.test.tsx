import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../test/test-utils'
import ResidentCard from './ResidentCard'
import { apiClient } from '../../api/client'
import type { ResidentListItem } from '../../types/api'

/** Кнопка «🎬 Видео о регистрации» — только у «Не завершил регистрацию»,
 *  после отправки сутки вместо неё «Видео отправлено · дата» (2026-11-05). */

function incomplete(overrides: Partial<ResidentListItem> = {}): ResidentListItem {
  return {
    id: 7,
    first_name: 'Рамис',
    last_name: null,
    phone: null,
    status: 'pending',
    verification_status: 'pending',
    primary_address: null,
    apartments_count: 0,
    bot_blocked: false,
    ...overrides,
  } as ResidentListItem
}

const VIDEO_BUTTON = { name: /Видео о регистрации/ }

describe('ResidentCard — видео о регистрации', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('не завершил — клик шлёт видео и не открывает карточку', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { sent: true } })
    render(<ResidentCard resident={incomplete()} />)

    fireEvent.click(screen.getByRole('button', VIDEO_BUTTON))

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/api/v2/residents/7/send-registration-video'))
  })

  it.each([
    ['с телефоном', { phone: '+998901112233' }],
    ['с квартирой', { apartments_count: 1 }],
    ['одобрен', { status: 'approved' }],
  ] as const)('%s — кнопки нет', (_name, patch) => {
    render(<ResidentCard resident={incomplete(patch)} />)
    expect(screen.queryByRole('button', VIDEO_BUTTON)).not.toBeInTheDocument()
  })

  it('отправлено меньше суток назад — дата вместо кнопки', () => {
    const sentAt = new Date(Date.now() - 60 * 60 * 1000).toISOString()
    render(<ResidentCard resident={incomplete({ registration_video_sent_at: sentAt })} />)
    expect(screen.getByText(/Видео отправлено ·/)).toBeInTheDocument()
    expect(screen.queryByRole('button', VIDEO_BUTTON)).not.toBeInTheDocument()
  })

  it('отправлено больше суток назад — кнопка снова доступна', () => {
    const sentAt = new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString()
    render(<ResidentCard resident={incomplete({ registration_video_sent_at: sentAt })} />)
    expect(screen.getByRole('button', VIDEO_BUTTON)).toBeInTheDocument()
  })
})
