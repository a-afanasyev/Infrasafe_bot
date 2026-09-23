import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import i18n from '../../../i18n'
import TasksPage from './TasksPage'

vi.mock('../../twaClient', () => ({
  twaClient: {
    get: vi.fn().mockResolvedValue({
      data: [
        { request_number: '260923-001', status: 'В работе', category: 'Сантехника', description: 'x', created_at: '2026-09-23T10:00:00Z' },
        { request_number: '260923-002', status: 'Закуп', category: 'Сантехника', description: 'y', created_at: '2026-09-23T10:00:00Z' },
      ],
    }),
  },
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TasksPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TasksPage — A9-P2-31', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('uz')
  })

  it('заголовки групп статусов локализованы (uz без кириллицы)', async () => {
    renderPage()
    const headers = await screen.findAllByRole('heading', { level: 2 })
    expect(headers).toHaveLength(2)
    for (const h of headers) {
      expect(h.textContent).not.toMatch(/[А-Яа-яЁё]/)
    }
  })
})
