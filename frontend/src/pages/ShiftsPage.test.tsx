import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useCallback, useState, type ReactNode } from 'react'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, fireEvent, within } from '../test/test-utils'
import { server } from '../test/msw/server'
import { TopbarContext } from '../contexts/topbar'
import type { ShiftBrief } from '../hooks/useShifts'
import ShiftsPage from './ShiftsPage'

// TEST-068: страница «Смены» — три вида (день/неделя/месяц) с навигацией по
// датам в display-зоне, карточки статистики, передачи/шаблоны, открытие
// деталей смены из ленты. WebSocket глушится, «сегодня» — фиксированное.

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  readyState = 0
  onopen: (() => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }
  close() {
    this.readyState = 3
  }
}

/** Тулбар живёт в контексте: без провайдера действия страницы не рендерятся. */
function TopbarHarness({ children }: { children: ReactNode }) {
  const [actions, setActions] = useState<ReactNode>(null)
  // Стабильная ссылка: эффект страницы зависит от clearActions, новая функция
  // на каждый рендер = бесконечный цикл setActions.
  const clearActions = useCallback(() => setActions(null), [])
  return (
    <TopbarContext.Provider value={{ actions, setActions, clearActions }}>
      <div data-testid="topbar">{actions}</div>
      {children}
    </TopbarContext.Provider>
  )
}

function makeShift(overrides: Partial<ShiftBrief> = {}): ShiftBrief {
  return {
    id: 5,
    user_id: 10,
    executor_name: 'Иван Тестов',
    status: 'active',
    shift_type: 'regular',
    start_time: '2026-06-08T10:00:00+05:00',
    end_time: '2026-06-08T12:00:00+05:00',
    max_requests: 5,
    current_request_count: 1,
    load_percentage: 40,
    specialization_focus: ['electrician'],
    ...overrides,
  }
}

const STATS = { active_shifts: 3, active_executors: 2, coverage_pct: 80, avg_efficiency: null, shifts_today: 3, pending_transfers: 1 }
const TRANSFER = { id: 1, shift_id: 5, from_executor_name: 'Иван Тестов', to_executor_name: 'Пётр Второй', status: 'pending', reason: 'Болею', urgency_level: 'normal', created_at: '2026-06-08T05:00:00Z' }
const TEMPLATE = { id: 1, name: 'Ночная', description: null, start_hour: 22, start_minute: 0, duration_hours: 8, default_shift_type: 'regular', days_of_week: null, is_active: true, min_executors: 1, max_executors: 3 }

let scheduleParams: Array<{ date_from: string; date_to: string }>

function installHandlers(shifts: ShiftBrief[]) {
  server.use(
    http.get('*/api/v2/shifts/schedule', ({ request }) => {
      const u = new URL(request.url)
      scheduleParams.push({ date_from: u.searchParams.get('date_from') ?? '', date_to: u.searchParams.get('date_to') ?? '' })
      return HttpResponse.json(shifts)
    }),
    http.get('*/api/v2/shifts/stats', () => HttpResponse.json(STATS)),
    http.get('*/api/v2/shifts/transfers', () => HttpResponse.json([TRANSFER])),
    http.get('*/api/v2/shifts/templates', () => HttpResponse.json([TEMPLATE])),
    http.get('*/api/v2/shifts/employees', () => HttpResponse.json([])),
    http.get('*/api/v2/auto-manager-config', () => HttpResponse.json({ enabled: false, window_start: '22:00', window_end: '06:00' })),
    http.get('*/api/v2/shifts/5', () => HttpResponse.json({ ...makeShift(), notes: null, specialization_focus: null, coverage_areas: null, priority_level: 3, completed_requests: 0, efficiency_score: null, quality_rating: null, template_id: null, created_at: null })),
  )
}

async function renderPage() {
  render(
    <TopbarHarness>
      <ShiftsPage />
    </TopbarHarness>,
  )
  await waitFor(() => expect(screen.getByText('Расписание смен')).toBeInTheDocument())
}

beforeEach(() => {
  scheduleParams = []
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  // Только Date: таймеры msw/RTL остаются настоящими. Понедельник 8 июня 2026, Ташкент.
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-06-08T09:00:00+05:00'))
  installHandlers([makeShift(), makeShift({ id: 6, user_id: 20, executor_name: 'Пётр Второй', load_percentage: 60, specialization_focus: ['plumber'] })])
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('ShiftsPage — вид «день»', () => {
  it('метка даты, карточки статистики, лента, передачи и шаблоны; WS на shifts', async () => {
    await renderPage()
    expect(screen.getByText('Понедельник, 8 июня 2026')).toBeInTheDocument()
    expect(FakeWebSocket.instances.at(-1)?.url).toMatch(/\/ws\/v2\/shifts$/)

    // Статистика: исполнителей 2, покрытие 80 %, спец-покрытие 2/3 → 67 %, передач 1, нагрузка (40+60)/2.
    const card = (label: string) => screen.getByText(label).parentElement as HTMLElement
    expect(card('Исполнителей на смене')).toHaveTextContent('2')
    expect(card('Покрытие %')).toHaveTextContent('80%')
    expect(card('Покрытие спец-ций')).toHaveTextContent('67%')
    expect(card('Передачи')).toHaveTextContent('1')
    expect(card('Общая нагрузка')).toHaveTextContent('50%')

    // Лента дня и тепловая карта дня.
    expect(screen.getAllByText('10:00 — 12:00 · Активна')).toHaveLength(2)
    expect(screen.getByText('Тепловая карта покрытия')).toBeInTheDocument()

    // Передачи (бейдж-счётчик) и шаблоны.
    const transfersTitle = screen.getByText('Запросы на передачу')
    expect(within(transfersTitle.parentElement as HTMLElement).getByText('1')).toBeInTheDocument()
    expect(screen.queryByText('Нет запросов на передачу')).toBeNull()
    expect(screen.getByText('Ночная')).toBeInTheDocument()
    expect(screen.getByText('22:00 · 8ч')).toBeInTheDocument()

    // Тулбар: переключатель видов и кнопка создания.
    const topbar = screen.getByTestId('topbar')
    expect(within(topbar).getByRole('button', { name: '+ Создать смену' })).toBeInTheDocument()
    expect(within(topbar).getByRole('button', { name: 'Шаблоны' })).toBeInTheDocument()
  })

  it('«След. день»/«Пред. день» сдвигают дату и перезапрашивают расписание; «Сегодня» возвращает', async () => {
    await renderPage()
    const first = scheduleParams[0]
    fireEvent.click(screen.getByRole('button', { name: 'След. день' }))
    expect(await screen.findByText('Вторник, 9 июня 2026')).toBeInTheDocument()
    await waitFor(() => expect(scheduleParams.length).toBe(2))
    expect(scheduleParams[1].date_from).toBe(first.date_to) // окно [полночь, полночь) сдвинулось ровно на день
    // Смена периода — новый queryKey → спиннер вместо страницы: ждём метку после каждого шага.
    fireEvent.click(screen.getByRole('button', { name: 'Пред. день' }))
    expect(await screen.findByText('Понедельник, 8 июня 2026')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Пред. день' }))
    expect(await screen.findByText('Воскресенье, 7 июня 2026')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Сегодня' }))
    expect(await screen.findByText('Понедельник, 8 июня 2026')).toBeInTheDocument()
  })

  it('клик по смене в ленте открывает «Детали смены»; «+ Создать смену» открывает диалог', async () => {
    await renderPage()
    fireEvent.click(screen.getAllByText('10:00 — 12:00 · Активна')[0])
    expect(await screen.findByText('Детали смены #5')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Закрыть' }).at(-1) as HTMLElement)
    await waitFor(() => expect(screen.queryByText('Детали смены #5')).toBeNull())

    fireEvent.click(within(screen.getByTestId('topbar')).getByRole('button', { name: '+ Создать смену' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('пустой период: нагрузка 0 %, «Нет смен», нет передач и шаблонов', async () => {
    installHandlers([])
    server.use(
      http.get('*/api/v2/shifts/transfers', () => HttpResponse.json([])),
      http.get('*/api/v2/shifts/templates', () => HttpResponse.json([])),
    )
    await renderPage()
    expect(screen.getByText('Нет смен')).toBeInTheDocument()
    expect(screen.getByText('Нет запросов на передачу')).toBeInTheDocument()
    expect(screen.getByText('Нет шаблонов')).toBeInTheDocument()
    expect((screen.getByText('Общая нагрузка').parentElement as HTMLElement)).toHaveTextContent('0%')
  })
})

describe('ShiftsPage — «неделя» и «месяц»', () => {
  it('неделя: метка Пн–Вс, карта покрытия недели вместо дневной, шаг навигации 7 дней', async () => {
    await renderPage()
    fireEvent.click(within(screen.getByTestId('topbar')).getByRole('tab', { name: 'Неделя' }))
    expect(await screen.findByText('Неделя 8 – 14 июня 2026')).toBeInTheDocument()
    expect(screen.getByText('Покрытие по часам и дням недели')).toBeInTheDocument()
    expect(screen.queryByText('Тепловая карта покрытия')).toBeNull()
    expect(screen.getByRole('button', { name: 'Эта неделя' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Пред. неделя' }))
    expect(await screen.findByText('Неделя 1 – 7 июня 2026')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Пред. неделя' }))
    expect(await screen.findByText('Неделя 25 – 31 мая 2026')).toBeInTheDocument()
    // Неделя через границу месяца — обе даты с месяцем.
    fireEvent.click(await screen.findByRole('button', { name: 'Эта неделя' }))
    expect(await screen.findByText('Неделя 8 – 14 июня 2026')).toBeInTheDocument()
    for (const label of ['Неделя 15 – 21 июня 2026', 'Неделя 22 – 28 июня 2026', 'Неделя 29 июня – 5 июля 2026']) {
      fireEvent.click(await screen.findByRole('button', { name: 'След. неделя' }))
      expect(await screen.findByText(label)).toBeInTheDocument()
    }
  })

  it('месяц: метка «июня 2026», шаг — месяц; клик по дню в карте уводит в неделю этого дня', async () => {
    await renderPage()
    fireEvent.click(within(screen.getByTestId('topbar')).getByRole('tab', { name: 'Месяц' }))
    expect(await screen.findByText('июня 2026')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Этот месяц' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'След. месяц' }))
    expect(await screen.findByText('июля 2026')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Этот месяц' }))
    expect(await screen.findByText('июня 2026')).toBeInTheDocument()

    // Календарная карта месяца: 17 июня → неделя 15–21.
    fireEvent.click(await screen.findByTitle(/^17\.6 · /))
    expect(await screen.findByText('Неделя 15 – 21 июня 2026')).toBeInTheDocument()
  })
})
