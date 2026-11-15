import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import type { CleaningBuilding, CleaningPlanView, CleaningStaff } from '../../types/cleaning'
import CleaningPlanPage from './CleaningPlanPage'
import CleaningStaffPage from './CleaningStaffPage'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const BUILDING: CleaningBuilding = {
  id: 1, address: 'д. 12', yard_id: 1, floor_count: 9, entrance_count: 3, has_plan: true,
  show_to_residents: false, show_photos: false,
  entrances: [{ entrance: 1, user_id: 11 }, { entrance: 2, user_id: 11 }, { entrance: 3, user_id: null }],
}
const PLAN: CleaningPlanView = {
  building_id: 1, floor_count: 9, entrance_count: 3, upcoming: null, uncovered: {}, snapshot_mismatch: false,
  current: {
    id: 5, valid_from: '2026-11-10', valid_to: null, extra_points: [], floor_count: 9, entrance_count: 3,
    items: [{ work_kind: 'wet', weekdays: [0, 3], floor_from: 1, floor_to: 5 }],
  },
}
const STAFF: CleaningStaff = {
  norm: 20,
  unassigned: [{ building_id: 1, entrance: 3 }],
  cleaners: [
    { user_id: 11, first_name: 'Дилноза', last_name: 'К', entrances: [{ building_id: 1, entrance: 1 }, { building_id: 1, entrance: 2 }],
      by_weekday: [27, 0, 0, 27, 0, 0, 0], buildings: { 1: [27, 0, 0, 27, 0, 0, 0] }, week: 54, peak: 27, percent: 135, overloaded: true },
    { user_id: 12, first_name: 'Зухра', last_name: 'Т', entrances: [], by_weekday: [0, 0, 0, 0, 0, 0, 0], buildings: {},
      week: 0, peak: 0, percent: 0, overloaded: false },
  ],
}

beforeEach(() => {
  useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: false })
  server.use(
    http.get('*/api/v2/cleaning/buildings', () => HttpResponse.json({ buildings: [BUILDING] })),
    http.get('*/api/v2/cleaning/buildings/1/plan', () => HttpResponse.json(PLAN)),
    http.get('*/api/v2/cleaning/staff', () => HttpResponse.json(STAFF)),
  )
})

describe('CleaningPlanPage', () => {
  it('показывает пропуск этажей по черновику и шлёт план после правки', async () => {
    let body: unknown = null
    server.use(http.put('*/api/v2/cleaning/buildings/1/plan', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json(PLAN.current)
    }))
    const user = userEvent.setup()
    render(<CleaningPlanPage />)

    expect(await screen.findByText('не моются этажи: 6, 7, 8, 9')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Этажи, строка 1'), 'all')
    expect(screen.getByText('все этажи покрыты')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Вт, строка 1' }))
    await user.click(screen.getByRole('button', { name: 'Сохранить план' }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({ items: [{ work_kind: 'wet', weekdays: [0, 1, 3] }], extra_points: [] })
  })

  it('не даёт сохранить работу без дней', async () => {
    const user = userEvent.setup()
    render(<CleaningPlanPage />)
    await screen.findByLabelText('Этажи, строка 1')
    await user.click(screen.getByRole('button', { name: 'Пн, строка 1' }))
    await user.click(screen.getByRole('button', { name: 'Чт, строка 1' }))
    expect(screen.getByRole('button', { name: 'Сохранить план' })).toBeDisabled()
    expect(screen.getByText('У каждой работы должен быть хотя бы один день.')).toBeInTheDocument()
  })
})

describe('CleaningStaffPage', () => {
  it('показывает перегруз, подъезды без уборщицы и привязывает дом', async () => {
    let body: unknown = null
    server.use(http.put('*/api/v2/cleaning/assignments', async ({ request }) => {
      body = await request.json()
      return new HttpResponse(null, { status: 204 })
    }))
    const user = userEvent.setup()
    render(<CleaningStaffPage />)

    expect(await screen.findByText(/Перегруз: Дилноза К — 27 этажей в день при норме 20/)).toBeInTheDocument()
    expect(screen.getByText('Без уборщицы: д. 12, подъезд 3.')).toBeInTheDocument()
    // привязаны не все подъезды дома — в подписи видно какие
    expect(screen.getByText('д. 12 (1, 2)')).toBeInTheDocument()
    const row = screen.getByText('135% — перегруз').closest('tr') as HTMLElement
    expect(within(row).getByText('54')).toBeInTheDocument()

    // дом уже за другой уборщицей — перехват только после подтверждения
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await user.selectOptions(screen.getByLabelText('Привязать дом: Зухра Т'), '1')
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(body).toBeNull()

    confirm.mockReturnValue(true)
    await user.selectOptions(screen.getByLabelText('Привязать дом: Зухра Т'), '1')
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({ building_id: 1, entrances: null, user_id: 12 })

    // один подъезд, а не весь дом
    body = null
    const fields = screen.getAllByPlaceholderText('подъезды: все')
    await user.type(fields[fields.length - 1], '3')
    await user.selectOptions(screen.getByLabelText('Привязать дом: Зухра Т'), '1')
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({ building_id: 1, entrances: [3], user_id: 12 })
    confirm.mockRestore()
  })
})
