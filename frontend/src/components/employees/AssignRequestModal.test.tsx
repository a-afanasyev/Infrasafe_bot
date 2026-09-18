import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import type { RequestCard } from '../../hooks/useKanban'
import AssignRequestModal from './AssignRequestModal'

// TEST-068 (порция employees): назначение заявки сотруднику из списка канбана —
// только колонки «Новая»/«В работе»; PATCH /requests/{number} с executor_id.

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const EMPLOYEE: EmployeeBrief = {
  id: 5, first_name: 'Андрей', last_name: 'Афанасьев', phone: null, specialization: [],
  active_shift_id: null, verification_status: 'verified', status: 'approved', roles: ['executor'], bot_blocked: false,
}

function req(number: string, status: string, description: string | null = null): RequestCard {
  return {
    request_number: number, status, category: 'plumbing', urgency: null, source: null, description,
    address: null, executor_id: null, executor_name: null, notes: null, completion_report: null,
    requested_materials: null, return_reason: null, manager_return_reason: null,
    created_at: '2026-09-18T00:00:00Z', updated_at: null, manager_confirmed: false,
    elevator_id: null, elevator_label: null,
  }
}

function mockKanban(columns: { status: string; requests: RequestCard[] }[]) {
  server.use(http.get('*/api/v2/requests/kanban', () =>
    HttpResponse.json({ columns: columns.map((c) => ({ ...c, count: c.requests.length })) })))
}

describe('AssignRequestModal', () => {
  it('показывает только заявки из «Новая»/«В работе»; выбор → PATCH с executor_id, toast, закрытие', async () => {
    const user = userEvent.setup()
    mockKanban([
      { status: 'Новая', requests: [req('260918-001', 'Новая', 'Течёт кран')] },
      { status: 'Выполнена', requests: [req('260918-002', 'Выполнена')] },
      { status: 'В работе', requests: [req('260918-003', 'В работе')] },
    ])
    const patches: { number: string; body: unknown }[] = []
    server.use(http.patch('*/api/v2/requests/:number', async ({ params, request }) => {
      patches.push({ number: String(params.number), body: await request.json() })
      return HttpResponse.json({ ok: true })
    }))
    const onClose = vi.fn()
    render(<AssignRequestModal employee={EMPLOYEE} onClose={onClose} />)

    expect(screen.getByText('Назначить заявку')).toBeInTheDocument()
    expect(screen.getByText('Андрей Афанасьев')).toBeInTheDocument()
    expect(await screen.findByText('#260918-001')).toBeInTheDocument()
    expect(screen.getByText('Течёт кран')).toBeInTheDocument()
    expect(screen.getByText('#260918-003')).toBeInTheDocument()
    expect(screen.queryByText('#260918-002')).not.toBeInTheDocument()

    await user.click(screen.getByText('#260918-001').closest('button')!)

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(patches).toEqual([{ number: '260918-001', body: { executor_id: 5 } }])
    expect(toast.success).toHaveBeenCalledWith('Заявка обновлена')
  })

  it('нет назначаемых заявок — пустой текст', async () => {
    mockKanban([{ status: 'Выполнена', requests: [req('260918-002', 'Выполнена')] }])
    render(<AssignRequestModal employee={EMPLOYEE} onClose={() => {}} />)
    expect(await screen.findByText('Нет заявок для назначения')).toBeInTheDocument()
  })

  it('ошибка PATCH: toast.error, текст ошибки под списком, диалог открыт', async () => {
    const user = userEvent.setup()
    mockKanban([{ status: 'Новая', requests: [req('260918-001', 'Новая')] }])
    server.use(http.patch('*/api/v2/requests/:number', () => HttpResponse.json({ detail: 'x' }, { status: 409 })))
    const onClose = vi.fn()
    render(<AssignRequestModal employee={EMPLOYEE} onClose={onClose} />)

    await user.click((await screen.findByText('#260918-001')).closest('button')!)

    expect(await screen.findByText('Не удалось сохранить. Попробуйте снова.')).toBeInTheDocument()
    expect(toast.error).toHaveBeenCalledWith('Не удалось обновить заявку')
    expect(onClose).not.toHaveBeenCalled()
  })
})
