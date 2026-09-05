import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router'
import { render, screen, waitFor, within } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import { ELEVATOR_DETAIL } from '../../test/fixtures/elevators'
import type { ElevatorDetail, ElevatorOccurrence } from '../../types/elevators'
import ElevatorDetailPage from './ElevatorDetailPage'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

const OCC_CERT: ElevatorOccurrence = {
  id: 31, elevator_id: 7, elevator_label: ELEVATOR_DETAIL.label, kind: 'certification',
  due_on: '2026-10-01', state: 'planned', done_at: null, done_by_user_id: null,
  comment: null, request_number: null, created_at: null,
}

function mockDetail(detail: ElevatorDetail) {
  server.use(
    http.get('*/api/v2/elevators/7', () => HttpResponse.json(detail)),
    http.get('*/api/v2/elevators/7/events', () => HttpResponse.json([])),
    http.get('*/api/v2/elevators/7/occurrences', () => HttpResponse.json([OCC_CERT])),
    http.get('*/api/v2/elevators/7/requests', () =>
      HttpResponse.json([
        { request_number: '260905-001', status: 'Выполнена', category: 'elevator', urgency: 'high', created_at: '2026-09-05T09:00:00Z', elevator_operational: false, executor_name: 'Иван Петров', applicant_name: null },
        { request_number: '260905-002', status: 'Новая', category: 'elevator', urgency: 'low', created_at: null, elevator_operational: null, executor_name: null, applicant_name: 'Анна' },
      ]),
    ),
  )
}

function renderPage() {
  return render(
    <Routes>
      <Route path="/dashboard/elevators/:id" element={<ElevatorDetailPage />} />
    </Routes>,
    { routerEntries: ['/dashboard/elevators/7'] },
  )
}

beforeEach(() => {
  useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: false })
})

describe('ElevatorDetailPage', () => {
  it('шапка: label, адрес, счётчик квартир без подъезда', async () => {
    mockDetail(ELEVATOR_DETAIL)
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })).toBeInTheDocument()
    expect(screen.getByText(/Квартир без подъезда: 4/)).toBeInTheDocument()
    expect(screen.getByText('OTIS')).toBeInTheDocument()
  })

  it('ссылка на акт: http(s) — <a>, javascript: — просто текст', async () => {
    mockDetail({ ...ELEVATOR_DETAIL, cert_act_url: 'javascript:alert(1)' })
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    expect(screen.getByText('javascript:alert(1)')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'javascript:alert(1)' })).toBeNull()
  })

  it('ссылка на акт https — кликабельна с rel=noreferrer', async () => {
    mockDetail(ELEVATOR_DETAIL)
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    const link = screen.getByRole('link', { name: 'https://example.org/act.pdf' })
    expect(link).toHaveAttribute('href', 'https://example.org/act.pdf')
    expect(link.getAttribute('rel')).toContain('noreferrer')
  })

  it('кнопки статусов disabled, если лифт не введён в эксплуатацию', async () => {
    mockDetail({ ...ELEVATOR_DETAIL, is_commissioned: false, current_status: null })
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    await user.click(screen.getByRole('button', { name: 'Статус' }))
    expect(screen.getByText('Смена статуса недоступна: лифт не введён в эксплуатацию')).toBeInTheDocument()
    for (const name of ['Работает', 'Не работает', 'В ремонте', 'Техобслуживание']) {
      expect(screen.getByRole('button', { name })).toBeDisabled()
    }
  })

  it('введён: кнопка другого статуса активна, текущий — disabled; диалог шлёт PUT', async () => {
    let body: Record<string, unknown> | null = null
    mockDetail(ELEVATOR_DETAIL)
    server.use(
      http.put('*/api/v2/elevators/7/status', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ changed: true, old_status: 'working', new_status: 'not_working', status_since: null, notified_residents: 5 })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    await user.click(screen.getByRole('button', { name: 'Статус' }))
    expect(screen.getByRole('button', { name: 'Работает' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Не работает' }))
    await user.type(screen.getByLabelText('Причина (необязательно)'), 'застрял')
    await user.click(screen.getByRole('button', { name: 'Сменить статус' }))
    await waitFor(() => expect(body).toEqual({ status: 'not_working', reason: 'застрял' }))
  })

  it('complete certification требует номер/срок/ссылку на акт', async () => {
    let posted = false
    mockDetail(ELEVATOR_DETAIL)
    server.use(
      http.post('*/api/v2/elevators/occurrences/31/complete', () => {
        posted = true
        return HttpResponse.json({ ...OCC_CERT, state: 'done' })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    await user.click(screen.getByRole('button', { name: 'Календарь' }))
    await user.click(await screen.findByRole('button', { name: 'Выполнено' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Выполнено' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Заполните номер, срок действия и ссылку на акт')
    expect(posted).toBe(false)

    await user.type(within(dialog).getByLabelText('Номер освидетельствования'), 'CERT-10')
    await user.type(within(dialog).getByLabelText('Освидетельствование до'), '2027-10-01')
    await user.type(within(dialog).getByLabelText('Ссылка на акт'), 'https://example.org/act2.pdf')
    await user.click(within(dialog).getByRole('button', { name: 'Выполнено' }))
    await waitFor(() => expect(posted).toBe(true))
  })

  it('bulk-confirm: чекбокс только у «Выполнена», результат per-item', async () => {
    let body: Record<string, unknown> | null = null
    mockDetail(ELEVATOR_DETAIL)
    server.use(
      http.post('*/api/v2/elevators/requests/bulk-confirm', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json([
          { request_number: '260905-001', ok: true, error_kind: null, error: null },
        ])
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    await user.click(screen.getByRole('button', { name: /Заявки/ }))
    await screen.findByText('№260905-001')
    expect(screen.getByRole('checkbox', { name: '260905-001' })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: '260905-002' })).toBeNull()
    const confirm = screen.getByRole('button', { name: 'Подтвердить выбранные' })
    expect(confirm).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: '260905-001' }))
    await user.click(confirm)
    await waitFor(() => expect(body).toEqual({ request_numbers: ['260905-001'] }))
    expect(await screen.findByText(/260905-001 — подтверждена/)).toBeInTheDocument()
  })

  it('после bulk-confirm один раз спрашивает «Лифт работает?»; выбор шлёт PUT с номером заявки', async () => {
    let putBody: Record<string, unknown> | null = null
    mockDetail(ELEVATOR_DETAIL)
    server.use(
      http.post('*/api/v2/elevators/requests/bulk-confirm', () =>
        HttpResponse.json([
          { request_number: '260905-001', ok: true, error_kind: null, error: null },
        ])),
      http.put('*/api/v2/elevators/7/status', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ changed: true, old_status: 'working', new_status: 'not_working', status_since: null, notified_residents: 1 })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    await user.click(screen.getByRole('button', { name: /Заявки/ }))
    await user.click(await screen.findByRole('checkbox', { name: '260905-001' }))
    await user.click(screen.getByRole('button', { name: 'Подтвердить выбранные' }))

    const dialog = await screen.findByRole('dialog', { name: 'Лифт работает?' })
    await user.click(within(dialog).getByRole('button', { name: 'Не работает' }))
    await waitFor(() =>
      expect(putBody).toEqual({
        status: 'not_working',
        reason: 'подтверждение заявки 260905-001',
        request_number: '260905-001',
      }),
    )
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Лифт работает?' })).toBeNull())
  })

  it('bulk-confirm без успешных заявок — подсказки нет, ошибки списком', async () => {
    mockDetail(ELEVATOR_DETAIL)
    server.use(
      http.post('*/api/v2/elevators/requests/bulk-confirm', () =>
        HttpResponse.json([
          { request_number: '260905-001', ok: false, error_kind: 'invalid_transition', error: 'уже подтверждена' },
        ])),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    await user.click(screen.getByRole('button', { name: /Заявки/ }))
    await user.click(await screen.findByRole('checkbox', { name: '260905-001' }))
    await user.click(screen.getByRole('button', { name: 'Подтвердить выбранные' }))

    expect(await screen.findByText(/260905-001 — ошибка: уже подтверждена/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Лифт работает?' })).toBeNull()
  })

  it('«Создать ремонт» шлёт колл-центровый payload с elevator_id', async () => {
    let body: Record<string, unknown> | null = null
    mockDetail(ELEVATOR_DETAIL)
    server.use(
      http.post('*/api/v2/callcenter/requests', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ request_number: '260905-003' }, { status: 201 })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    await user.click(screen.getByRole('button', { name: /Заявки/ }))
    await user.click(await screen.findByRole('button', { name: 'Создать ремонт' }))
    await user.type(screen.getByLabelText('Описание'), 'Не едет')
    await user.click(screen.getByRole('button', { name: 'Создать заявку' }))
    await waitFor(() =>
      expect(body).toEqual({
        category: 'elevator', urgency: 'high', description: 'Не едет',
        building_id: 12, address: ELEVATOR_DETAIL.building_address, elevator_id: 7,
        elevator_operational: false, acceptance_mode: 'manager',
      }),
    )
  })

  it('executor: нет кнопок правки/приёмки, но смена статуса доступна', async () => {
    useAuthStore.setState({ user: { id: 2, roles: ['executor'] }, isAuthenticated: true, hydrating: false })
    mockDetail(ELEVATOR_DETAIL)
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('heading', { name: 'Лифт 1, подъезд 2' })
    expect(screen.queryByRole('link', { name: 'Редактировать' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Архивировать' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Статус' }))
    expect(screen.getByRole('button', { name: 'Не работает' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: /Заявки/ }))
    await screen.findByText('№260905-001')
    expect(screen.queryByRole('button', { name: 'Подтвердить выбранные' })).toBeNull()
  })
})
