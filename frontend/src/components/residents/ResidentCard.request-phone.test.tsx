import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../test/test-utils'
import ResidentCard from './ResidentCard'
import { apiClient } from '../../api/client'
import type { ResidentListItem } from '../../types/api'

/**
 * Кнопка «Запросить номер» на карточке жителя (2026-08-27): житель без
 * телефона получает в Telegram запрос поделиться контактом. Кнопка НЕ должна
 * открывать карточку жителя (карточка целиком кликабельна — stopPropagation).
 */

function makeResident(overrides: Partial<ResidentListItem> = {}): ResidentListItem {
  return {
    id: 5,
    first_name: 'Назима',
    last_name: 'Алексеевна',
    phone: null,
    status: 'approved',
    verification_status: 'verified',
    primary_address: 'Дом 23 · кв. 5',
    apartments_count: 1,
    bot_blocked: false,
    ...overrides,
  } as ResidentListItem
}

describe('ResidentCard — запрос номера телефона', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('без телефона — кнопка, клик шлёт запрос и НЕ открывает карточку', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { sent: true } })
    render(<ResidentCard resident={makeResident()} />)

    fireEvent.click(screen.getByRole('button', { name: /Запросить номер/ }))

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/api/v2/residents/5/request-phone'))
  })

  it('с телефоном кнопки нет', () => {
    render(<ResidentCard resident={makeResident({ phone: '+998901112233' })} />)
    expect(screen.getByText('+998901112233')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Запросить номер/ })).not.toBeInTheDocument()
  })
})
