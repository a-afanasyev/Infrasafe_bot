import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../test/test-utils'
import { server } from '../test/msw/server'
import FeedbackPage from './FeedbackPage'

const ITEMS = [
  { id: 1, type: 'complaint', status: 'new', text: 'Лифт сломан', has_media: true, author_name: 'Иван', created_at: null },
  { id: 2, type: 'wish', status: 'resolved', text: 'Больше зелени', has_media: false, author_name: 'Пётр', created_at: null },
]

describe('Dashboard FeedbackPage', () => {
  it('renders the feedback list', async () => {
    server.use(
      http.get('*/api/v2/feedback', () => HttpResponse.json({ items: ITEMS, total: 2 })),
    )
    render(<FeedbackPage />)
    expect(await screen.findByText('Лифт сломан')).toBeInTheDocument()
    expect(screen.getByText('Больше зелени')).toBeInTheDocument()
  })

  it('sets document.title (QA-03)', async () => {
    server.use(
      http.get('*/api/v2/feedback', () => HttpResponse.json({ items: ITEMS, total: 2 })),
    )
    render(<FeedbackPage />)
    await screen.findByText('Лифт сломан')
    expect(document.title).toContain('Обратная связь')
    expect(document.title).toContain('UK Management')
  })

  it('sends status filter as a query param', async () => {
    const urls: string[] = []
    server.use(
      http.get('*/api/v2/feedback', ({ request }) => {
        urls.push(request.url)
        return HttpResponse.json({ items: ITEMS, total: 2 })
      }),
    )
    const user = userEvent.setup()
    render(<FeedbackPage />)
    await screen.findByText('Лифт сломан')
    await user.click(screen.getByRole('button', { name: 'Решено' }))
    await waitFor(() => expect(urls.some((u) => u.includes('status=resolved'))).toBe(true))
  })

  it('opens detail modal and allows a status change (PATCH)', async () => {
    let patched: Record<string, unknown> | null = null
    server.use(
      http.get('*/api/v2/feedback', () => HttpResponse.json({ items: ITEMS, total: 2 })),
      http.get('*/api/v2/feedback/1', () =>
        HttpResponse.json({
          id: 1, type: 'complaint', status: 'new', text: 'Лифт сломан', source: 'twa',
          media_ids: [], reply: null, replied_at: null, author_name: 'Иван', author_phone: null, created_at: null,
        }),
      ),
      http.patch('*/api/v2/feedback/1', async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          id: 1, type: 'complaint', status: 'in_review', text: 'Лифт сломан', source: 'twa',
          media_ids: [], reply: null, replied_at: null, author_name: 'Иван', author_phone: null, created_at: null,
        })
      }),
    )
    const user = userEvent.setup()
    render(<FeedbackPage />)
    await user.click(await screen.findByText('Лифт сломан'))
    // модалка загрузила деталь — кнопка смены статуса "В работе" доступна
    const btn = await screen.findByRole('button', { name: 'В работе' })
    await user.click(btn)
    await waitFor(() => expect(patched).toEqual({ status: 'in_review' }))
  })
})
