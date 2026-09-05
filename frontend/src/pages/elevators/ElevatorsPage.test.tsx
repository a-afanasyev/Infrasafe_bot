import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import { ELEVATOR_CARD, ELEVATOR_SUMMARY } from '../../test/fixtures/elevators'
import ElevatorsPage from './ElevatorsPage'

function mockRegistry() {
  const urls: URL[] = []
  server.use(
    http.get('*/api/v2/elevators/summary', () => HttpResponse.json(ELEVATOR_SUMMARY)),
    http.get('*/api/v2/addresses/yards', () => HttpResponse.json([{ id: 3, name: 'Двор 3' }])),
    http.get('*/api/v2/elevators', ({ request }) => {
      urls.push(new URL(request.url))
      return HttpResponse.json({ items: [ELEVATOR_CARD, { ...ELEVATOR_CARD, id: 8, label: 'Лифт 2, подъезд 2', current_status: null, is_commissioned: false }], total: 2 })
    }),
  )
  return urls
}

beforeEach(() => {
  useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: false })
})

describe('ElevatorsPage', () => {
  it('рендерит сводку и таблицу по мокам', async () => {
    mockRegistry()
    render(<ElevatorsPage />)
    expect(await screen.findByText('Лифт 1, подъезд 2')).toBeInTheDocument()
    expect(screen.getByText('Лифт 2, подъезд 2')).toBeInTheDocument()
    // сводка: всего 5, заявок без лифта 3
    expect(screen.getByText('Всего лифтов')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('Лифтовых заявок без лифта')).toBeInTheDocument()
    // доступность 30д и бейдж «не введён» у второго лифта
    expect(screen.getAllByText('97 %').length).toBe(2)
    expect(screen.getAllByText('Не введён').length).toBeGreaterThan(0)
    expect(document.title).toContain('Лифты')
  })

  it('фильтр по статусу меняет запрос списка', async () => {
    const urls = mockRegistry()
    const user = userEvent.setup()
    render(<ElevatorsPage />)
    await screen.findByText('Лифт 1, подъезд 2')
    await user.selectOptions(screen.getByLabelText('Статус'), 'not_working')
    await waitFor(() => expect(urls.at(-1)?.searchParams.get('status')).toBe('not_working'))
    expect(urls.at(-1)?.searchParams.get('offset')).toBe('0')
    // флаг-чекбокс уходит повторяющимся параметром
    await user.click(screen.getByLabelText('Без договора'))
    await waitFor(() => expect(urls.at(-1)?.searchParams.getAll('flag')).toEqual(['no_contract']))
  })

  it('«Добавить лифт» и «Настройки» видны manager', async () => {
    mockRegistry()
    render(<ElevatorsPage />)
    await screen.findByText('Лифт 1, подъезд 2')
    expect(screen.getByRole('link', { name: /Добавить лифт/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Настройки/ })).toBeInTheDocument()
  })

  it('«Добавить лифт» скрыта у executor', async () => {
    useAuthStore.setState({ user: { id: 2, roles: ['executor'] }, isAuthenticated: true, hydrating: false })
    mockRegistry()
    render(<ElevatorsPage />)
    await screen.findByText('Лифт 1, подъезд 2')
    expect(screen.queryByRole('link', { name: /Добавить лифт/ })).toBeNull()
    expect(screen.queryByRole('link', { name: /Настройки/ })).toBeNull()
    // календарь доступен всем читателям
    expect(screen.getByRole('link', { name: /Календарь/ })).toBeInTheDocument()
  })
})
