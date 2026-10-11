import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '../test/test-utils'
import { server } from '../test/msw/server'
import type {
  BacklogOut,
  AddressStatsOut,
  ChannelStatsOut,
  CostStatsOut,
  ExecutorStatsRow,
  QualityStatsOut,
  RequestStatsOut,
  ShiftStatsOut,
  StatsKpi,
} from '../types/api'
import AnalyticsPage from './AnalyticsPage'
import { useAuthStore } from '../stores/authStore'
import { actionsFor } from '../test/authz'

// Аналитика: календарные периоды и срезы, вкладки, исполнители и CSV.
// Графики recharts в jsdom не меряются — проверяются KPI, таблицы, заглушки и
// параметры запросов.

vi.mock('../utils/timezone', async (orig) => ({
  ...(await orig<typeof import('../utils/timezone')>()),
  todayInDisplayTz: () => '2026-10-12',
}))

const SHIFTS: ShiftStatsOut = { active_shifts: 3, active_executors: 4, coverage_pct: 80, avg_efficiency: null, shifts_today: 3, pending_transfers: 0 }
const KPI: StatsKpi = {
  created: 42, accepted: 30, avg_assign_hours: 1.2, avg_work_hours: 3.25, avg_to_accept_hours: 20.5,
  avg_satisfaction: 4.6, returned: 2,
}
const OVERVIEW: RequestStatsOut = {
  date_from: '2026-10-01', date_to: '2026-10-12', granularity: 'day',
  series: [{ bucket: '2026-10-01', created: 5, accepted: 2 }],
  by_category: { plumbing: 7, heating: 3 },
  open_by_status: { 'Новая': 3, 'В работе': 1 },
  kpi: KPI,
  previous: { ...KPI, created: 35, accepted: 30 },
}
const EXECUTORS: ExecutorStatsRow[] = [
  { user_id: 7, name: 'Иван Петров', executed: 12, accepted: 10, returned: 1, overdue: 2, avg_work_hours: 3.5,
    avg_to_accept_hours: 20, avg_rating: 4.8, ratings_count: 5, in_work_now: 3, materials_cost: 1500 },
  { user_id: 8, name: 'Олег Сидоров', executed: 2, accepted: 0, returned: 0, overdue: 0, avg_work_hours: null,
    avg_to_accept_hours: null, avg_rating: null, ratings_count: 0, in_work_now: 1, materials_cost: 0 },
]
const QUALITY: QualityStatsOut = {
  sla_hours: { critical: 4, high: 24, medium: 72, low: 168 },
  by_urgency: [{ urgency: 'high', sla_hours: 24, accepted: 4, measured: 4, median_hours: 10, p90_hours: 30, overdue: 1 }],
  returns_by_category: [{ category: 'plumbing', accepted: 4, returned: 1 }],
  ratings: { '1': 0, '2': 0, '3': 1, '4': 0, '5': 3 },
  recent_reviews: [{ request_number: '261001-001', rating: 5, review: 'Спасибо, быстро', executor_name: 'Иван Петров', completed_at: '2026-10-02T05:00:00Z' }],
}
const BACKLOG: BacklogOut = {
  total: 2, by_age: { lt1: 1, d1_3: 0, d3_7: 0, d7_30: 0, gt30: 1 },
  queues: [{ user_id: null, name: null, open: 1, oldest_age_days: 40 }],
  oldest: [{ request_number: '260901-001', status: 'Новая', category: 'plumbing', created_at: '2026-09-01T05:00:00Z', executor_id: null, executor_name: null, age_days: 40 }],
}
const ADDRESSES: AddressStatsOut = {
  buildings: [{ id: 1, name: 'ул. Садовая, 5', count: 4 }], yards: [],
  repeats: [{ request_number: '261020-101', previous_number: '261002-101', address: 'кв. 12', category: 'plumbing', days_after: 18 }],
}
const CHANNELS: ChannelStatsOut = { granularity: 'day', totals: { bot: 3, twa: 1 }, series: [{ bucket: '2026-10-01', counts: { bot: 3, twa: 1 } }] }
const COSTS: CostStatsOut = { total: 150, requests_with_materials: 1, accepted: 3, by_category: { electricity: 150 }, by_building: [] }

let calls: Record<string, URLSearchParams[]>
const seen = (path: string) => calls[path] ?? []

beforeEach(() => {
  calls = {}
  useAuthStore.setState({ user: { id: 1, roles: ['manager'], actions: actionsFor(['manager']) }, isAuthenticated: true, hydrating: false })
  const track = (path: string, body: unknown) =>
    http.get(`*/api/v2/requests/stats${path}`, ({ request }) => {
      ;(calls[path] ??= []).push(new URL(request.url).searchParams)
      return HttpResponse.json(body)
    })
  server.use(
    http.get('*/api/v2/shifts/stats', () => HttpResponse.json(SHIFTS)),
    track('', OVERVIEW),
    track('/executors', EXECUTORS),
    track('/quality', QUALITY),
    track('/backlog', BACKLOG),
    track('/addresses', ADDRESSES),
    track('/channels', CHANNELS),
    track('/costs', COSTS),
    http.get('*/api/v2/auto-manager-config', () => HttpResponse.json({
      enabled: false, mode: 'rule', window_start: '20:00', window_end: '08:00', timezone: 'Asia/Tashkent',
      max_requests_per_run: 10, sla_hours: QUALITY.sla_hours,
    })),
  )
})

describe('AnalyticsPage', () => {
  it('по умолчанию — этот месяц, авто-срез; KPI с изменением к прошлому окну', async () => {
    render(<AnalyticsPage />)
    expect(await screen.findByText('42')).toBeInTheDocument()
    const params = seen('')[0]
    expect(params.get('date_from')).toBe('2026-10-01')
    expect(params.get('date_to')).toBe('2026-10-12')
    expect(params.get('granularity')).toBeNull()
    expect(screen.getByText('↑ 20%')).toBeInTheDocument() // создано 42 против 35
    expect(screen.getByText('3.3')).toBeInTheDocument() // работа исполнителя
    expect(screen.getByText('4.6')).toBeInTheDocument()
    expect(screen.getByText('Сантехника')).toBeInTheDocument()
    expect(screen.getByText('Новая')).toBeInTheDocument()
    expect(await screen.findByText('на смене сейчас: 4')).toBeInTheDocument()
    // вкладки, которые не открыты, не грузятся
    expect(seen('/executors')).toHaveLength(0)
  })

  it('пресет «прошлый год» и ручной срез уходят в запрос', async () => {
    const user = userEvent.setup()
    render(<AnalyticsPage />)
    await screen.findByText('42')
    await user.click(screen.getByRole('button', { name: 'Прошлый год' }))
    await waitFor(() => expect(seen('').at(-1)?.get('date_from')).toBe('2025-01-01'))
    expect(seen('').at(-1)?.get('date_to')).toBe('2025-12-31')
    await user.click(screen.getByRole('button', { name: 'месяцы' }))
    await waitFor(() => expect(seen('').at(-1)?.get('granularity')).toBe('month'))
    expect(screen.getByRole('button', { name: 'дни' })).toBeEnabled() // 365 дней — ещё можно
    await user.click(screen.getByRole('button', { name: 'Этот год' }))
    await user.clear(screen.getByLabelText('С даты'))
    await user.type(screen.getByLabelText('С даты'), '2024-01-01')
    expect(screen.getByRole('button', { name: 'дни' })).toBeDisabled() // больше года
  })

  it('исполнители: таблица, раскрытие строки с принятыми заявками за период', async () => {
    const user = userEvent.setup()
    let listParams: URLSearchParams | null = null
    server.use(http.get('*/api/v2/requests', ({ request }) => {
      listParams = new URL(request.url).searchParams
      return HttpResponse.json([{ request_number: '261005-001', category: 'plumbing', address: 'ул. Садовая, 5' }])
    }))
    render(<AnalyticsPage />)
    await screen.findByText('42')
    await user.click(screen.getByRole('button', { name: 'Исполнители' }))
    const row = (await screen.findByText('Иван Петров')).closest('tr')!
    expect(within(row).getByText('12')).toBeInTheDocument()
    expect(within(row).getByText('10')).toBeInTheDocument()
    expect(within(row).getByText('4.8')).toBeInTheDocument()
    await user.click(row)
    expect(await screen.findByText('#261005-001')).toHaveAttribute('href', '/dashboard?request=261005-001')
    expect(listParams!.get('executor_id')).toBe('7')
    expect(listParams!.get('accepted_from')).toBe('2026-10-01')
    expect(listParams!.get('accepted_to')).toBe('2026-10-12')
    // у Олега нет принятых — строка не раскрывается и без кнопки выгрузки
    const oleg = screen.getByText('Олег Сидоров').closest('tr')!
    expect(within(oleg).queryByRole('button')).toBeNull()
  })

  it('сроки и качество, хвост и адреса, каналы и затраты', async () => {
    const user = userEvent.setup()
    render(<AnalyticsPage />)
    await screen.findByText('42')

    await user.click(screen.getByRole('button', { name: 'Сроки и качество' }))
    expect(await screen.findByText('Спасибо, быстро')).toBeInTheDocument()
    expect(screen.getAllByText('1 (25%)')).toHaveLength(2) // просрочки и возвраты
    expect(screen.getByRole('button', { name: 'Сохранить нормативы' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Хвост и адреса' }))
    expect(await screen.findByText('#260901-001')).toBeInTheDocument()
    expect(screen.getByText('ул. Садовая, 5')).toBeInTheDocument()
    expect(screen.getByText('#261002-101')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Каналы и затраты' }))
    expect(await screen.findByText('Mini App')).toBeInTheDocument()
    expect(screen.getAllByText('150').length).toBeGreaterThan(0)
  })

  it('ошибка запроса — баннер; невалидный период — подсказка и без запроса', async () => {
    server.use(http.get('*/api/v2/requests/stats', () => HttpResponse.json({ detail: 'x' }, { status: 500 })))
    const user = userEvent.setup()
    render(<AnalyticsPage />)
    expect(await screen.findByText('Не удалось загрузить данные аналитики. Проверьте соединение.')).toBeInTheDocument()
    const from = screen.getByLabelText('С даты')
    await user.clear(from)
    expect(screen.getByText('Укажите корректный период (не длиннее 5 лет)')).toBeInTheDocument()
  })
})
