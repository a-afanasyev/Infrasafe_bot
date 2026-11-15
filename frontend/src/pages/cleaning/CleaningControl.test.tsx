import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import { addDays, isoDate, mondayOf, monthRange, shortDate } from '../../features/cleaning/dates'
import type { CleaningTaskCard, CleaningTaskRow } from '../../types/cleaning'
import CleaningControlPage from './CleaningControlPage'
import CleaningTaskPage from './CleaningTaskPage'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const TODAY = isoDate(new Date())
const row = (over: Partial<CleaningTaskRow>): CleaningTaskRow => ({
  id: 1, building_id: 1, address: 'д. 12', entrance: 1, work_date: TODAY, status: 'accepted', responsible_id: 11,
  slots_total: 4, slots_done: 4, sampled: false, ...over,
})
const CARD: CleaningTaskCard = {
  task: row({ id: 2, entrance: 2, status: 'review', slots_done: 2 }), version: 5, works: ['wet'],
  slots_required: ['floor:1', 'floor:2', 'floor:3'], session_opened_at: null,
  current: [
    { id: 31, slot: 'floor:1', outcome: 'activated', refusal_code: null, trust_level: 'live', received_at: '2026-11-17T06:00:00Z', client_captured_at: null, has_file: false },
    { id: 32, slot: 'floor:2', outcome: 'activated', refusal_code: null, trust_level: 'offline', received_at: '2026-11-17T06:01:00Z', client_captured_at: null, has_file: false },
  ],
  evidence: [{ id: 33, slot: 'floor:3', outcome: 'evidence', refusal_code: null, trust_level: 'late', received_at: '2026-11-17T19:00:00Z', client_captured_at: null, has_file: false }],
  other: [],
  events: [{ kind: 'completed', actor_id: null, from_status: 'in_progress', to_status: 'review', reason: null,
             payload: { reasons: ['similar_photo', 'too_fast'], sampled: false }, created_at: '2026-11-17T06:02:00Z' }],
  complaints: [],
}

beforeEach(() => {
  useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: false })
  server.use(
    http.get('*/api/v2/cleaning/control/tasks', () => HttpResponse.json({
      date_from: TODAY, date_to: TODAY,
      tasks: [row({}), row({ id: 2, entrance: 2, status: 'review', slots_done: 2, sampled: true })],
    })),
    http.get('*/api/v2/cleaning/control/complaints', () => HttpResponse.json({ complaints: [
      { id: 9, building_id: 1, entrance: 2, work_date: TODAY, author_id: 5, task_id: 2, request_number: null, outcome: 'pending', created_at: null },
    ] })),
    http.get('*/api/v2/cleaning/control/timesheet', () => HttpResponse.json({ date_from: TODAY, date_to: TODAY, rows: [
      { user_id: 11, first_name: 'Дилноза', last_name: 'К', planned: 20, accepted: 18, rejected: 1, expired: 1, missed: 0, complaints: 2, confirmed: 1, percent: 90 },
    ] })),
    http.get('*/api/v2/cleaning/rules', () => HttpResponse.json({ version: 3, data: {
      day_end_time: '20:00', sample_every: 10, session_ttl_minutes: 120, allow_deferred_auto: false } })),
    http.get('*/api/v2/cleaning/control/tasks/2', () => HttpResponse.json(CARD)),
    http.get('*/api/v2/cleaning/staff', () => HttpResponse.json({ norm: 40, cleaners: [], unassigned: [] })),
  )
})

describe('dates', () => {
  it('понедельник недели, сдвиг дней, границы месяца', () => {
    expect(mondayOf('2026-11-17')).toBe('2026-11-16')
    expect(mondayOf('2026-11-16')).toBe('2026-11-16')
    expect(mondayOf('2026-11-22')).toBe('2026-11-16')
    expect(addDays('2026-11-30', 1)).toBe('2026-12-01')
    expect(monthRange('2026-02-10')).toEqual(['2026-02-01', '2026-02-28'])
    expect(shortDate('2026-11-07')).toBe('07.11')
  })
})

describe('CleaningControlPage', () => {
  it('показывает сводку дня, матрицу, очередь, жалобу и табель; сохраняет конец дня', async () => {
    let complaintBody: unknown = null
    let rulesBody: unknown = null
    server.use(
      http.post('*/api/v2/cleaning/control/complaints/9/decision', async ({ request }) => {
        complaintBody = await request.json()
        return HttpResponse.json({})
      }),
      http.put('*/api/v2/cleaning/rules', async ({ request }) => {
        rulesBody = await request.json()
        return HttpResponse.json({ version: 4, data: {} })
      }),
    )
    const user = userEvent.setup()
    render(<CleaningControlPage />)

    expect(await screen.findByRole('link', { name: 'Убрано 4/4' })).toHaveAttribute('href', '/dashboard/cleaning/tasks/1')
    expect(screen.getByRole('link', { name: 'Проверить 2/4' })).toBeInTheDocument()
    expect(screen.getByText('Очередь на проверку — 1')).toBeInTheDocument()
    expect(screen.getByText('выборочный контроль')).toBeInTheDocument()
    expect(await screen.findByText('заявка ещё не создана')).toBeInTheDocument()
    expect(await screen.findByText('2 / 1')).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Подтвердилась' }))
    await waitFor(() => expect(complaintBody).toEqual({ outcome: 'confirmed' }))

    const dayEnd = await screen.findByLabelText('Конец дня уборки')
    expect(dayEnd).toHaveValue('20:00')
    await user.clear(dayEnd)
    await user.type(dayEnd, '21:30')
    await user.click(screen.getByRole('button', { name: 'Сохранить настройки' }))
    await waitFor(() => expect(rulesBody).toEqual(
      { day_end_time: '21:30', sample_every: 10, session_ttl_minutes: 120, allow_deferred_auto: false }))
  })
})

describe('CleaningTaskPage', () => {
  const renderCard = () => render(
    <Routes><Route path="/dashboard/cleaning/tasks/:id" element={<CleaningTaskPage />} /></Routes>,
    { routerEntries: ['/dashboard/cleaning/tasks/2'] },
  )

  it('объясняет, почему задание на проверке, и не даёт отклонить без комментария', async () => {
    let body: unknown = null
    server.use(http.post('*/api/v2/cleaning/control/tasks/2/decision', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json(CARD.task)
    }))
    const user = userEvent.setup()
    renderCard()

    expect(await screen.findByText('Кадр почти совпадает с прошлым фото этого этажа')).toBeInTheDocument()
    expect(screen.getByText('Этажи сняты слишком быстро')).toBeInTheDocument()
    expect(screen.getByText('Не сняты: Этаж 3')).toBeInTheDocument()
    expect(screen.getByText('Поздние и неучтённые фото')).toBeInTheDocument()
    expect(screen.getByText(/без сессии/)).toBeInTheDocument()

    const reject = screen.getByRole('button', { name: 'Отклонить' })
    expect(reject).toBeDisabled()
    await user.type(screen.getByLabelText(/Комментарий/), 'этаж 3 не снят')
    await user.click(reject)
    await waitFor(() => expect(body).toEqual({ to: 'rejected', version: 5, comment: 'этаж 3 не снят' }))
  })
})
