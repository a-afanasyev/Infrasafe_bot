import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import { actionsFor } from '../../test/authz'
import type { ProblemsStatusOut } from '../../types/api'
import type { DateRange } from '../../utils/analyticsPeriod'
import ProblemsTab from './ProblemsTab'

// Вкладка ИИ-разбора: общий отчёт (видят все с аналитикой), запуск в фоне (202)
// + опрос статуса, ограничения из «Правил ИИ», последние разборы.

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

function asRoles(roles: string[]) {
  useAuthStore.setState({ user: { id: 1, roles, actions: actionsFor(roles) }, isAuthenticated: true, hydrating: false })
}

function renderTab(range: DateRange = RANGE, onPickRange = vi.fn()) {
  render(<ProblemsTab range={range} onPickRange={onPickRange} />)
  return onPickRange
}

beforeEach(() => {
  posts = []
  asRoles(['manager'])
  status = {
    available: true, running: false, busy: false, failed: false,
    next_run_at: null, runs_left: 10, report: null, recent: [],
  }
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
    renderTab()
    expect(await screen.findByText('Течь в доме 5')).toBeInTheDocument()
    expect(screen.getByText('Месяц спокойный, кроме дома 5')).toBeInTheDocument()
    expect(screen.getByText('Критично')).toBeInTheDocument()
    expect(screen.getByText('Дом / двор')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '#261005-001' })).toHaveAttribute('href', '/dashboard?request=261005-001')
    expect(screen.getByRole('button', { name: /Разобрать заново/ })).toBeEnabled()
    expect(screen.getByText('Осталось запусков сегодня: 10')).toBeInTheDocument()
  })

  it('без права запуска отчёт виден, кнопки нет', async () => {
    asRoles(['engineer'])
    status = { ...status, report: REPORT }
    renderTab()
    expect(await screen.findByText('Течь в доме 5')).toBeInTheDocument()
    expect(screen.getByText(/Запускает его менеджер/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Разобрать заново|Найти проблемы/ })).not.toBeInTheDocument()
  })

  it('запускает разбор за период и показывает, что идёт', async () => {
    renderTab()
    await userEvent.click(await screen.findByRole('button', { name: /Найти проблемы/ }))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].get('date_from')).toBe('2026-10-01')
    expect(posts[0].get('date_to')).toBe('2026-10-31')
    expect(await screen.findByRole('button', { name: /Идёт разбор/ })).toBeDisabled()
  })

  it('слишком часто — кнопка ждёт времени из ограничений', async () => {
    status = { ...status, report: REPORT, next_run_at: new Date(Date.now() + 30 * 60_000).toISOString() }
    renderTab()
    expect(await screen.findByText(/Следующий разбор можно запустить после/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Разобрать заново/ })).toBeDisabled()
  })

  it('ограничение кончилось — кнопка оживает сама, без перезагрузки', async () => {
    let calls = 0
    server.use(http.get(PATH, () => HttpResponse.json(++calls === 1
      ? { ...status, report: REPORT, next_run_at: new Date(Date.now() + 500).toISOString() }
      : { ...status, report: REPORT })))
    renderTab()
    expect(await screen.findByRole('button', { name: /Разобрать заново/ })).toBeDisabled()
    await waitFor(() => expect(screen.getByRole('button', { name: /Разобрать заново/ })).toBeEnabled(),
      { timeout: 4000 })
    expect(calls).toBe(2)
  })

  it('последние разборы других периодов открываются кликом', async () => {
    status = {
      ...status,
      recent: [
        { first: '2026-10-01', last: '2026-10-31', generated_at: '2026-11-01T07:00:00Z' },
        { first: '2026-09-01', last: '2026-09-30', generated_at: '2026-10-01T07:00:00Z' },
      ],
    }
    const onPick = renderTab()
    await userEvent.click(await screen.findByRole('button', { name: '01.09.2026 — 30.09.2026' }))
    expect(onPick).toHaveBeenCalledWith({ from: '2026-09-01', to: '2026-09-30' })
    expect(screen.queryByRole('button', { name: '01.10.2026 — 31.10.2026' })).not.toBeInTheDocument()
  })

  it('без ИИ на площадке кнопка выключена', async () => {
    status = { ...status, available: false }
    renderTab()
    expect(await screen.findByText('ИИ на площадке не подключён.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Найти проблемы/ })).toBeDisabled()
  })

  it('слишком длинный период не запускается', async () => {
    renderTab({ from: '2026-01-01', to: '2026-12-31' })
    expect(await screen.findByText(/не длиннее 92 дней/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Найти проблемы/ })).toBeDisabled()
  })

  it('пока идёт разбор другого периода — кнопка ждёт', async () => {
    status = { ...status, busy: true }
    renderTab()
    expect(await screen.findByText(/идёт разбор другого периода/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Найти проблемы/ })).toBeDisabled()
  })

  it('сообщает о неудачном прогоне', async () => {
    status = { ...status, failed: true }
    renderTab()
    expect(await screen.findByText(/Разбор не удался/)).toBeInTheDocument()
  })

  it('отказ сервера при запуске — текст ошибки, кнопка снова доступна', async () => {
    server.use(http.post(PATH, () => HttpResponse.json({ detail: 'Исчерпан лимит' }, { status: 409 })))
    renderTab()
    const button = await screen.findByRole('button', { name: /Найти проблемы/ })
    await userEvent.click(button)
    await waitFor(() => expect(screen.getByRole('button', { name: /Найти проблемы/ })).toBeEnabled())
  })
})
