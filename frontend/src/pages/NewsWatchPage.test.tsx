import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { render } from '../test/test-utils'
import { server } from '../test/msw/server'
import NewsWatchPage from './NewsWatchPage'

const CONFIG = {
  sources: [{ chat: '@toshkent_elektr', title: 'Электросети' }],
  complex_context: 'ЖК Тест',
  keywords: ['отключ', 'suv'],
  auto_publish: false,
  min_confidence: 0.8,
  broadcast: { dm: true, residents_groups: true },
}

const ITEM = {
  id: 7, source_chat_id: -1001, source_message_id: 3, chat_title: 'Электросети',
  raw_text: 'Плановое отключение 29.10', posted_at: null, kind: 'power', relevant: true,
  confidence: 0.92, summary_ru: '29.10 10:00–16:00 нет света', summary_uz: '29.10 chiroq yo‘q',
  starts_at: null, ends_at: null, status: 'pending', published_at: null, decided_by: null,
  broadcast_status: 'none', broadcast_attempts: 0, broadcast_details: null, created_at: null,
}

beforeEach(() => {
  server.use(
    http.get('*/api/v2/news-watch/config', () => HttpResponse.json(CONFIG)),
    http.get('*/api/v2/news-watch/items', ({ request }) => {
      const status = new URL(request.url).searchParams.get('status')
      return HttpResponse.json(status === 'pending' ? { items: [ITEM], total: 1 } : { items: [], total: 0 })
    }),
  )
})

describe('NewsWatchPage', () => {
  it('renders the pending queue and publishes an item', async () => {
    const posted: string[] = []
    server.use(
      http.post('*/api/v2/news-watch/items/:id/:decision', ({ params }) => {
        posted.push(`${params.id}/${params.decision}`)
        return HttpResponse.json({ ...ITEM, status: 'published', broadcast_status: 'pending' })
      }),
    )
    const user = userEvent.setup()
    render(<NewsWatchPage />)
    expect(await screen.findByText('29.10 10:00–16:00 нет света')).toBeInTheDocument()
    expect(screen.getByText('Электричество')).toBeInTheDocument()
    expect(screen.getByText(/уверенность 92%/)).toBeInTheDocument()
    await user.click(screen.getByText('Опубликовать'))
    await waitFor(() => expect(posted).toEqual(['7/publish']))
  })

  it('saves config from the form (sources parsed from lines)', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.put('*/api/v2/news-watch/config', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(body)
      }),
    )
    const user = userEvent.setup()
    render(<NewsWatchPage />)
    const sources = await screen.findByLabelText('Источники (по одному на строку: @канал Название)')
    expect(sources).toHaveValue('@toshkent_elektr Электросети')
    await user.clear(sources)
    await user.type(sources, '@suv_taminoti Водоканал{enter}@hokimiyat')
    await user.click(screen.getByLabelText('Публиковать автоматически при высокой уверенности'))
    await user.click(screen.getByText('Сохранить настройки'))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({
      sources: [{ chat: '@suv_taminoti', title: 'Водоканал' }, { chat: '@hokimiyat', title: '' }],
      complex_context: 'ЖК Тест',
      keywords: ['отключ', 'suv'],
      auto_publish: true,
      min_confidence: 0.8,
    })
  })

  it('shows empty state on other tabs', async () => {
    const user = userEvent.setup()
    render(<NewsWatchPage />)
    await screen.findByText('29.10 10:00–16:00 нет света')
    await user.click(screen.getByText('Отклонены'))
    expect(await screen.findByText('Пусто')).toBeInTheDocument()
  })
})
