import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import type { ShiftDetail } from '../../types/api'
import CreateShiftModal from './CreateShiftModal'

function noop() {}

const EMPLOYEES = [
  { id: 1, first_name: 'Андрей', last_name: 'Афанасьев', phone: '+998901112233' },
]

// 08:00Z = 13:00 Tashkent; 08:00Z next day = 13:00 Tashkent (a 24h shift).
const EDIT_SHIFT: ShiftDetail = {
  id: 67,
  user_id: 1,
  executor_name: 'Андрей Афанасьев',
  status: 'planned',
  shift_type: 'regular',
  start_time: '2026-06-05T08:00:00Z',
  end_time: '2026-06-06T08:00:00Z',
  max_requests: 20,
  current_request_count: 0,
  load_percentage: 0,
  specialization_focus: ['electrician'],
  notes: 'Плановая смена',
  coverage_areas: null,
  priority_level: 4,
  completed_requests: 0,
  efficiency_score: null,
  quality_rating: null,
  template_id: null,
  created_at: null,
}

beforeEach(() => {
  server.use(
    http.get('*/api/v2/shifts/employees', () => HttpResponse.json(EMPLOYEES)),
  )
})

describe('CreateShiftModal — create mode', () => {
  it('shows the create title and no delete button', () => {
    render(<CreateShiftModal isOpen onClose={noop} />)
    expect(screen.getByText('Создать смену')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Удалить смену' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Создать' })).toBeInTheDocument()
  })
})

describe('CreateShiftModal — edit mode', () => {
  it('shows the edit title and pre-fills fields from the shift', () => {
    render(<CreateShiftModal isOpen onClose={noop} shift={EDIT_SHIFT} />)
    expect(screen.getByText('Редактировать смену')).toBeInTheDocument()
    // start/end times pre-filled in Tashkent wall-clock
    expect(screen.getByDisplayValue('2026-06-05T13:00')).toBeInTheDocument()
    expect(screen.getByDisplayValue('2026-06-06T13:00')).toBeInTheDocument()
    expect(screen.getByDisplayValue('20')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Плановая смена')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeInTheDocument()
  })

  it('surfaces an executor not in the employees list as a selected option', () => {
    // user_id 99 is not in EMPLOYEES → without the fallback the select would
    // show the empty placeholder instead of the real executor.
    render(
      <CreateShiftModal
        isOpen
        onClose={noop}
        shift={{ ...EDIT_SHIFT, user_id: 99, executor_name: 'Отабек Тураев' }}
      />,
    )
    const option = screen.getByRole('option', { name: 'Отабек Тураев' }) as HTMLOptionElement
    expect(option).toBeInTheDocument()
    expect(option.selected).toBe(true)
  })

  it('shows the delete button for a planned shift', () => {
    render(<CreateShiftModal isOpen onClose={noop} shift={EDIT_SHIFT} />)
    expect(screen.getByRole('button', { name: 'Удалить смену' })).toBeInTheDocument()
  })

  it('hides the delete button for a non-planned (active) shift', () => {
    render(<CreateShiftModal isOpen onClose={noop} shift={{ ...EDIT_SHIFT, status: 'active' }} />)
    expect(screen.queryByRole('button', { name: 'Удалить смену' })).not.toBeInTheDocument()
  })

  it('PATCHes the shift by id on save with the edited fields', async () => {
    let patchedId: string | null = null
    let posted: Record<string, unknown> | null = null
    server.use(
      http.patch('*/api/v2/shifts/:id', async ({ request, params }) => {
        patchedId = String(params.id)
        posted = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 67 })
      }),
    )
    const user = userEvent.setup()
    render(<CreateShiftModal isOpen onClose={noop} shift={EDIT_SHIFT} />)

    const maxInput = screen.getByDisplayValue('20')
    await user.clear(maxInput)
    await user.type(maxInput, '15')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    await waitFor(() => expect(posted).not.toBeNull())
    expect(patchedId).toBe('67')
    expect(posted).toMatchObject({
      shift_type: 'regular',
      max_requests: 15,
      priority_level: 4,
      specialization_focus: ['electrician'],
    })
    // REG-02: смена исполнителя только через /reassign — PATCH НЕ шлёт user_id
    expect(posted).not.toHaveProperty('user_id')
    // times sent as ISO instants
    expect(posted).toHaveProperty('start_time')
    expect(posted).toHaveProperty('end_time')
  })
})
