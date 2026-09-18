import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../test/test-utils'
import { server } from '../test/msw/server'
import type { RequestStatsOut, ShiftStatsOut } from '../types/api'
import AnalyticsPage from './AnalyticsPage'

// TEST-068 (порция pages): страница аналитики — KPI, статусы с долями, топ
// исполнителей, лента событий, пустые состояния, смена периода → новый запрос,
// ошибка одного из запросов → баннер. Графики recharts в jsdom не меряются —
// проверяются легенда/центр диаграммы и заглушки.

const SHIFTS: ShiftStatsOut = { active_shifts: 3, active_executors: 4, coverage_pct: 80, avg_efficiency: null, shifts_today: 3, pending_transfers: 0 }
const REQUESTS: RequestStatsOut = {
  by_day: [{ date: '2026-09-17', created: 5, closed: 2 }],
  by_category: { plumbing: 7, heating: 3 },
  by_status: { 'Новая': 3, 'В работе': 1 },
  top_executors: [
    { user_id: 1, name: 'Андрей Афанасьев', completed: 12, avg_hours: 3.25, score: 98 },
    { user_id: 2, name: null, completed: 1, avg_hours: null, score: 15 },
  ],
  recent_actions: [
    { event_type: 'completed', request_number: '260918-001', executor_name: 'Андрей Афанасьев', created_at: '2026-09-18T05:00:00Z' },
    { event_type: 'unknown_event', request_number: '260918-002', executor_name: null, created_at: '2026-09-18T06:00:00Z' },
  ],
  total_requests: 42, avg_resolution_hours: 4.56, avg_satisfaction: null,
}

let periods: string[]
beforeEach(() => {
  periods = []
  server.use(
    http.get('*/api/v2/shifts/stats', () => HttpResponse.json(SHIFTS)),
    http.get('*/api/v2/requests/stats', ({ request }) => { periods.push(new URL(request.url).searchParams.get('period') ?? ''); return HttpResponse.json(REQUESTS) }),
  )
})

describe('AnalyticsPage', () => {
  it('KPI, статусы с процентами, топ исполнителей с рангами, лента событий; смена периода — новый запрос', async () => {
    const user = userEvent.setup()
    render(<AnalyticsPage />)

    expect(await screen.findByText('42')).toBeInTheDocument()
    expect(screen.getByText('4.6')).toBeInTheDocument() // avg_resolution_hours.toFixed(1)
    expect(screen.getByText('4')).toBeInTheDocument() // на смене сейчас
    expect(screen.getAllByText('—').length).toBeGreaterThan(0) // удовлетворённость null
    expect(periods).toEqual(['7d'])

    // статусы
    expect(screen.getByText('Новая')).toBeInTheDocument()
    expect(screen.getByText('В работе')).toBeInTheDocument()
    // категории — легенда пирога и центр (сумма)
    expect(screen.getByText('Сантехника')).toBeInTheDocument()
    expect(screen.getByText('Отопление')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
    // топ исполнителей
    expect(screen.getByText('🥇')).toBeInTheDocument()
    expect(screen.getByText('12 заявок · 3.3ч')).toBeInTheDocument()
    expect(screen.getByText('1 заявок · ?ч')).toBeInTheDocument()
    expect(screen.getByText('Неизвестно')).toBeInTheDocument()
    // лента событий: локализованный тип и неизвестный тип как есть
    expect(screen.getByText(/Завершена/)).toBeInTheDocument()
    expect(screen.getByText(/unknown_event/)).toBeInTheDocument()
    expect(screen.getByText('#260918-002')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '30 дней' }))
    await waitFor(() => expect(periods).toEqual(['7d', '30d']))
  })

  it('пустые данные — заглушки во всех блоках; ошибка одного запроса — баннер, остальное рендерится', async () => {
    server.use(
      http.get('*/api/v2/requests/stats', () => HttpResponse.json({ ...REQUESTS, by_day: [], by_category: {}, by_status: {}, top_executors: [], recent_actions: [] })),
      http.get('*/api/v2/shifts/stats', () => HttpResponse.json({ detail: 'x' }, { status: 500 })),
    )
    render(<AnalyticsPage />)
    expect(await screen.findByText('Не удалось загрузить данные аналитики. Проверьте соединение.')).toBeInTheDocument()
    expect(screen.getByText('Нет данных за выбранный период')).toBeInTheDocument()
    expect(screen.getByText('Категории за период отсутствуют')).toBeInTheDocument()
    expect(screen.getByText('Нет действий')).toBeInTheDocument()
    expect(screen.getAllByText('Нет данных').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/Обновлено:/)).toBeInTheDocument()
  })
})
