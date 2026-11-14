import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '../test/test-utils'
import { server } from '../test/msw/server'
import NoticesPage from './NoticesPage'

// Раздел «Новости и уведомления»: лента, форма, календарь.

const NEWS = {
  id: 1, kind: 'news', resource: null, source: 'manual', title_ru: 'Собрание жильцов', title_uz: '', text_ru: 'В 19:00',
  text_uz: '', place_ru: '', place_uz: '', icon: '', important: true, status: 'published', state: 'active',
  publish_at: '2026-11-13T05:00:00Z', starts_at: null, ends_at: null, all_day: false, expires_at: null,
  created_at: '2026-11-13T05:00:00Z',
}
const DRAFT = { ...NEWS, id: 2, title_ru: 'График уборки', important: false, status: 'draft', state: 'draft', publish_at: null }
const OUTAGE = {
  ...NEWS, id: 3, kind: 'outage', resource: 'power', source: 'news_watch', title_ru: 'Отключение электричества',
  important: false, state: 'scheduled', starts_at: '2026-11-18T05:00:00Z', ends_at: '2026-11-18T09:00:00Z',
}

type Body = Record<string, unknown>

function mockApi(items: unknown[] = [NEWS, DRAFT, OUTAGE]) {
  const calls: Array<{ method: string; path: string; body: Body | null }> = []
  const record = async (request: Request) => {
    const body = request.method === 'DELETE' ? null : ((await request.json().catch(() => null)) as Body | null)
    calls.push({ method: request.method, path: new URL(request.url).pathname.replace(/^.*\/api\/v2\/board-config/, ''), body })
  }
  server.use(
    http.get('*/api/v2/board-config/notices', () => HttpResponse.json({ items, total: items.length })),
    http.post('*/api/v2/board-config/notices', async ({ request }) => { await record(request); return HttpResponse.json(NEWS, { status: 201 }) }),
    http.patch('*/api/v2/board-config/notices/:id', async ({ request }) => { await record(request); return HttpResponse.json(NEWS) }),
    http.post('*/api/v2/board-config/notices/:id/:action', async ({ request }) => { await record(request); return HttpResponse.json(NEWS) }),
    http.delete('*/api/v2/board-config/notices/:id', async ({ request }) => { await record(request); return new HttpResponse(null, { status: 204 }) }),
  )
  return calls
}

describe('NoticesPage', () => {
  it('лента: записи с состоянием и источником; фильтр «Черновики»', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<NoticesPage />)

    const rows = await screen.findAllByTestId('notice-row')
    expect(rows).toHaveLength(3)
    expect(within(rows[0]).getByText('Опубликовано')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Важное')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Отключение · Электричество')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Из канала')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Запланировано')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Черновики' }))
    expect(screen.getAllByTestId('notice-row')).toHaveLength(1)
    expect(screen.getByText('График уборки')).toBeInTheDocument()
  })

  it('новость: без заголовка не сохраняется; «Опубликовать» шлёт POST с publish=true', async () => {
    const calls = mockApi([])
    const user = userEvent.setup()
    render(<NoticesPage />)

    await user.click(await screen.findByRole('button', { name: '+ Новость' }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Опубликовать' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Введите заголовок на русском')
    expect(calls).toHaveLength(0)

    const [titleRu, titleUz] = within(dialog).getAllByPlaceholderText(/^(RU|UZ)$/)
    await user.type(titleRu, 'Собрание')
    await user.type(titleUz, "Yig'ilish")
    await user.click(within(dialog).getByRole('button', { name: 'Опубликовать' }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'POST', path: '/notices' })
    expect(calls[0].body).toMatchObject({ kind: 'news', title_ru: 'Собрание', title_uz: "Yig'ilish", publish: true })
    expect(calls[0].body).not.toHaveProperty('starts_at') // null-поля на создании не уходят
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('черновик: «Опубликовать» и «Удалить» из ленты; опубликованную — «Снять с показа»', async () => {
    const calls = mockApi()
    const user = userEvent.setup()
    render(<NoticesPage />)

    const rows = await screen.findAllByTestId('notice-row')
    await user.click(within(rows[1]).getByRole('button', { name: 'Опубликовать' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    await user.click(within(screen.getAllByTestId('notice-row')[1]).getByRole('button', { name: 'Удалить' }))
    await waitFor(() => expect(calls).toHaveLength(2))
    await user.click(within(screen.getAllByTestId('notice-row')[0]).getByRole('button', { name: 'Снять с показа' }))
    await waitFor(() => expect(calls).toHaveLength(3))

    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      'POST /notices/2/publish', 'DELETE /notices/2', 'POST /notices/1/close',
    ])
  })

  it('календарь: клик по дню открывает плановое отключение на эту дату; правка — PATCH', async () => {
    const calls = mockApi()
    const user = userEvent.setup()
    render(<NoticesPage />, { routerEntries: ['/dashboard/notices?tab=calendar'] })

    expect(await screen.findByRole('tab', { name: 'Календарь' })).toHaveAttribute('aria-selected', 'true')
    const day = await waitFor(() => {
      const cell = document.querySelector('[data-day$="-15"]:not(.opacity-45)') as HTMLElement | null
      expect(cell).not.toBeNull()
      return cell as HTMLElement
    })
    await user.click(day)
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Плановое отключение' })).toBeInTheDocument()
    expect((within(dialog).getByLabelText('Начало') as HTMLInputElement).value).toMatch(/-15T10:00$/)
    await user.click(within(dialog).getByRole('button', { name: 'Отмена' }))

    // вкладка «Лента» → правка опубликованной записи
    await user.click(screen.getByRole('tab', { name: 'Лента' }))
    await user.click(within((await screen.findAllByTestId('notice-row'))[0]).getByRole('button', { name: 'Изменить' }))
    const edit = screen.getByRole('dialog')
    const titleRu = within(edit).getAllByPlaceholderText('RU')[0]
    await user.clear(titleRu)
    await user.type(titleRu, 'Перенос собрания')
    await user.click(within(edit).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toMatchObject({ method: 'PATCH', path: '/notices/1' })
    expect(calls[0].body).toMatchObject({ title_ru: 'Перенос собрания', important: true })
  })
})
