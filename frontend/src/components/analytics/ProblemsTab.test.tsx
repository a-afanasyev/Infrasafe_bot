import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import type { ProblemsStatusOut } from '../../types/api'
import ProblemsTab from './ProblemsTab'

// Вкладка ИИ-разбора: запуск в фоне (202) + опрос статуса, карточки проблем.

const RANGE = { from: '2026-10-01', to: '2026-10-31' }
const PATH = '*/api/v2/requests/stats/problems'

const REPORT: ProblemsStatusOut['report'] = {
  first: '2026-10-01', last: '2026-10-31', generated_at: '2026-11-01T07:00:00Z', model: 'm',
  request_count: 120, truncated: false,
  summary: { ru: 'Месяц спокойный, кроме дома 5', uz: 'Oy tinch' },
  problems: [{
    title: { ru: 'Течь в доме 5', uz: '5-uyda oqish' }, severity: 'critical', area: 'building',
    description: { ru: '4 заявки за месяц', uz: '4 ta' },
    recommendation: { ru: 'Осмотреть стояк', uz: 'Tekshirish' },
    evidence: ['261005-001', '261012-003'],
  }],
}

let status: ProblemsStatusOut
let posts: URLSearchParams[]

beforeEach(() => {
  posts = []
  status = { available: true, running: false, busy: false, failed: false, report: null }
  server.use(
    http.get(PATH, () => HttpResponse.json(status)),
    http.post(PATH, ({ request }) => {
      posts.push(new URL(request.url).searchParams)
      status = { ...status, running: true }
      return HttpResponse.json({ status: 'started' }, { status: 202 })
    }),
  )
})

describe('ProblemsTab', () => {
  it('показывает отчёт: итог, проблемы, ссылки на заявки', async () => {
    status = { ...status, report: REPORT }
    render(<ProblemsTab range={RANGE} />)
    expect(await screen.findByText('Течь в доме 5')).toBeInTheDocument()
    expect(screen.getByText('Месяц спокойный, кроме дома 5')).toBeInTheDocument()
    expect(screen.getByText('Критично')).toBeInTheDocument()
    expect(screen.getByText('Дом / двор')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '#261005-001' })).toHaveAttribute('href', '/dashboard?request=261005-001')
    expect(screen.getByRole('button', { name: /Разобрать заново/ })).toBeEnabled()
  })

  it('запускает разбор за период и показывает, что идёт', async () => {
    render(<ProblemsTab range={RANGE} />)
    await userEvent.click(await screen.findByRole('button', { name: /Найти проблемы/ }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].get('date_from')).toBe('2026-10-01')
    expect(posts[0].get('date_to')).toBe('2026-10-31')
    expect(await screen.findByRole('button', { name: /Идёт разбор/ })).toBeDisabled()
  })

  it('без ИИ на площадке кнопка выключена', async () => {
    status = { ...status, available: false }
    render(<ProblemsTab range={RANGE} />)
    expect(await screen.findByText('ИИ на площадке не подключён.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Найти проблемы/ })).toBeDisabled()
  })

  it('слишком длинный период не запускается', async () => {
    render(<ProblemsTab range={{ from: '2026-01-01', to: '2026-12-31' }} />)
    expect(await screen.findByText(/не длиннее 92 дней/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Найти проблемы/ })).toBeDisabled()
  })

  it('пока идёт разбор другого периода — кнопка ждёт', async () => {
    status = { ...status, busy: true }
    render(<ProblemsTab range={RANGE} />)
    expect(await screen.findByText(/идёт разбор другого периода/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Найти проблемы/ })).toBeDisabled()
  })

  it('сообщает о неудачном прогоне', async () => {
    status = { ...status, failed: true }
    render(<ProblemsTab range={RANGE} />)
    expect(await screen.findByText(/Разбор не удался/)).toBeInTheDocument()
  })

  it('отказ сервера при запуске — текст ошибки, кнопка снова доступна', async () => {
    server.use(http.post(PATH, () => HttpResponse.json({ detail: 'Исчерпан лимит' }, { status: 409 })))
    render(<ProblemsTab range={RANGE} />)
    const button = await screen.findByRole('button', { name: /Найти проблемы/ })
    await userEvent.click(button)
    await waitFor(() => expect(screen.getByRole('button', { name: /Найти проблемы/ })).toBeEnabled())
  })
})
