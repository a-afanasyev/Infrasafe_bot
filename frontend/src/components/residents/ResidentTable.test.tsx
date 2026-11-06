import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '../../test/test-utils'
import ResidentTable from './ResidentTable'
import { apiClient } from '../../api/client'
import type { ResidentListItem } from '../../types/api'

const navigate = vi.fn()
vi.mock('react-router', async importOriginal => ({
  ...(await importOriginal<typeof import('react-router')>()),
  useNavigate: () => navigate,
}))

/**
 * Табличный вид «Жителей» (2026-11-06): строки окрашены как карточки,
 * под ФИО — те же кнопки «Запросить номер» / «Видео о регистрации».
 */

function makeResident(overrides: Partial<ResidentListItem> = {}): ResidentListItem {
  return {
    id: 7,
    first_name: 'Назима',
    last_name: 'Алексеевна',
    phone: '+998901112233',
    status: 'approved',
    verification_status: 'verified',
    primary_address: 'Дом 23 · кв. 5',
    apartments_count: 1,
    bot_blocked: false,
    documents_submitted: false,
    created_at: '2026-11-06T08:25:00Z',
    ...overrides,
  } as ResidentListItem
}

const row = (name: RegExp) => screen.getByText(name).closest('tr') as HTMLElement

describe('ResidentTable — цвета строк и кнопки', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    navigate.mockClear()
  })

  it('тон строки совпадает с карточкой', () => {
    render(<ResidentTable residents={[
      makeResident({ id: 1, first_name: 'Синий', status: 'pending', verification_status: 'requested', documents_submitted: true }),
      makeResident({ id: 2, first_name: 'Жёлтый', status: 'pending', verification_status: 'pending' }),
      makeResident({ id: 3, first_name: 'Блок', bot_blocked: true }),
      makeResident({ id: 4, first_name: 'Петров' }),
    ]} />)
    expect(row(/Синий/).dataset.tone).toBe('submitted')
    expect(row(/Жёлтый/).dataset.tone).toBe('pending')
    expect(row(/Блок/).dataset.tone).toBe('botBlocked')
    expect(within(row(/Блок/)).getByText(/Бот заблокирован/)).toBeInTheDocument()
    expect(row(/Петров/).getAttribute('style') ?? '').not.toContain('background')
  })

  it('не завершил регистрацию — кнопки под ФИО, клик не открывает жителя', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { sent: true } })
    render(<ResidentTable residents={[
      makeResident({ phone: null, status: 'pending', verification_status: 'pending', apartments_count: 0 }),
    ]} />)
    const r = row(/Назима/)
    expect(r.dataset.tone).toBe('incomplete')
    // Контур тона — полоса на первой ячейке (у <tr> box-shadow рисуется не везде).
    expect(r.querySelector('td')?.getAttribute('style')).toContain('inset 3px')

    fireEvent.click(within(r).getByRole('button', { name: /Запросить номер/ }))
    fireEvent.click(within(r).getByRole('button', { name: /Видео о регистрации/ }))
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/api/v2/residents/7/request-phone')
      expect(post).toHaveBeenCalledWith('/api/v2/residents/7/send-registration-video')
    })
    expect(navigate).not.toHaveBeenCalled()

    // Клик по самой строке — открывает жителя (кнопки выше этого не делали).
    fireEvent.click(within(r).getByText(/Назима/))
    expect(navigate).toHaveBeenCalledWith('/dashboard/residents/7')
  })

  it('колонка «Регистрация» показывает дату', () => {
    render(<ResidentTable residents={[makeResident()]} />)
    expect(screen.getByText('Регистрация')).toBeInTheDocument()
    expect(within(row(/Назима/)).getByText(/06\.11\.2026/)).toBeInTheDocument()
  })
})
