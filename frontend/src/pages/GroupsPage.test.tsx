import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../test/test-utils'
import { server } from '../test/msw/server'
import GroupsPage from './GroupsPage'

const ITEMS = [
  { id: 1, chat_id: -1001234567890, title: 'Дом 12', kind: 'residents', is_active: true, require_tag: false, created_at: null, updated_at: null },
  { id: 2, chat_id: -1009876543210, title: 'Бригада', kind: 'staff', is_active: false, require_tag: true, created_at: null, updated_at: null },
]

describe('Dashboard GroupsPage', () => {
  it('renders the group list with kinds and statuses', async () => {
    server.use(
      http.get('*/api/v2/monitored-groups', () => HttpResponse.json({ items: ITEMS, total: 2 })),
    )
    render(<GroupsPage />)
    expect(await screen.findByText('Дом 12')).toBeInTheDocument()
    expect(screen.getByText('Бригада')).toBeInTheDocument()
    // Фаза 2: staff-группы обрабатываются — пометки «появится позже» больше нет
    expect(screen.queryByText(/обработка появится позже/)).toBeNull()
    expect(screen.getByText('Активна')).toBeInTheDocument()
    expect(screen.getByText('Выключена')).toBeInTheDocument()
  })

  it('creates a group via the form (POST body)', async () => {
    let posted: Record<string, unknown> | null = null
    server.use(
      http.get('*/api/v2/monitored-groups', () => HttpResponse.json({ items: [], total: 0 })),
      http.post('*/api/v2/monitored-groups', async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          { id: 3, chat_id: posted.chat_id, title: posted.title ?? null, kind: posted.kind, is_active: true },
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    render(<GroupsPage />)
    await screen.findByText('Группы пока не добавлены')

    await user.type(screen.getByPlaceholderText('-1001234567890'), '-1005555555555')
    await user.type(screen.getByPlaceholderText('Например: Дом 12, подъезд 1'), 'Новый дом')
    await user.click(screen.getByRole('button', { name: 'Добавить' }))

    await waitFor(() =>
      expect(posted).toEqual({ chat_id: -1005555555555, title: 'Новый дом', kind: 'residents' }),
    )
  })

  it('submit is disabled until chat_id is a valid number', async () => {
    server.use(
      http.get('*/api/v2/monitored-groups', () => HttpResponse.json({ items: [], total: 0 })),
    )
    const user = userEvent.setup()
    render(<GroupsPage />)
    const button = await screen.findByRole('button', { name: 'Добавить' })
    expect(button).toBeDisabled()
    await user.type(screen.getByPlaceholderText('-1001234567890'), 'abc')
    expect(button).toBeDisabled()
  })

  it('renders tag mode per group and toggles it (PATCH body)', async () => {
    let patched: Record<string, unknown> | null = null
    server.use(
      http.get('*/api/v2/monitored-groups', () => HttpResponse.json({ items: ITEMS, total: 2 })),
      http.patch('*/api/v2/monitored-groups/1', async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...ITEMS[0], require_tag: true })
      }),
    )
    const user = userEvent.setup()
    render(<GroupsPage />)
    // группа 2 в тег-режиме, группа 1 — нет
    expect(await screen.findByText('По тегу')).toBeInTheDocument()
    await user.click(screen.getByText('Все сообщения'))
    await waitFor(() => expect(patched).toEqual({ require_tag: true }))
  })

  it('toggles is_active (PATCH body)', async () => {
    let patched: Record<string, unknown> | null = null
    server.use(
      http.get('*/api/v2/monitored-groups', () => HttpResponse.json({ items: ITEMS, total: 2 })),
      http.patch('*/api/v2/monitored-groups/1', async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...ITEMS[0], is_active: false })
      }),
    )
    const user = userEvent.setup()
    render(<GroupsPage />)
    await user.click(await screen.findByText('Активна'))
    await waitFor(() => expect(patched).toEqual({ is_active: false }))
  })

  it('deletes only after inline confirmation', async () => {
    let deleted = false
    server.use(
      http.get('*/api/v2/monitored-groups', () => HttpResponse.json({ items: [ITEMS[0]], total: 1 })),
      http.delete('*/api/v2/monitored-groups/1', () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const user = userEvent.setup()
    render(<GroupsPage />)
    await user.click(await screen.findByLabelText('Удалить группу'))
    expect(deleted).toBe(false) // первый клик — только подтверждение
    await user.click(screen.getByRole('button', { name: 'Удалить?' }))
    await waitFor(() => expect(deleted).toBe(true))
  })

  it('sets document.title (QA-03)', async () => {
    server.use(
      http.get('*/api/v2/monitored-groups', () => HttpResponse.json({ items: [], total: 0 })),
    )
    render(<GroupsPage />)
    await screen.findByText('Группы пока не добавлены')
    expect(document.title).toContain('Группы Telegram')
  })
})
