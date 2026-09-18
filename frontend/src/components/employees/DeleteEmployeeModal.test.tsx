import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import DeleteEmployeeModal from './DeleteEmployeeModal'

// TEST-068 (порция employees): удаление сотрудника — два шага. Без активных
// заявок удаляем сразу; с активными — обязательный выбор преемника из пикера
// (пикер грузит широкую страницу /shifts/employees, msw).

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

function emp(overrides: Partial<EmployeeBrief> = {}): EmployeeBrief {
  return {
    id: 1, first_name: 'Андрей', last_name: 'Афанасьев', phone: '+998901112233',
    specialization: ['electrician'], active_shift_id: null, verification_status: 'verified',
    status: 'approved', roles: ['executor'], bot_blocked: false, ...overrides,
  }
}

const TARGETS = [
  emp({ id: 2, first_name: 'Борис', last_name: 'Петров', active_shift_id: 9 }),
  emp({ id: 3, first_name: 'Вера', last_name: 'Сидорова', status: 'blocked' }), // заблокированная — не преемник
  emp({ id: 1 }), // сам удаляемый — не преемник
]

function mockApi(activeCount: number) {
  const deletes: { id: string; body: unknown }[] = []
  server.use(
    http.get('*/api/v2/shifts/employees/:id/active-requests-count', () => HttpResponse.json({ count: activeCount })),
    http.get('*/api/v2/shifts/employees', () =>
      HttpResponse.json(TARGETS, { headers: { 'X-Total-Count': String(TARGETS.length) } })),
    http.patch('*/api/v2/shifts/employees/:id/delete', async ({ params, request }) => {
      deletes.push({ id: String(params.id), body: await request.json() })
      return HttpResponse.json({ ok: true })
    }),
  )
  return deletes
}

describe('DeleteEmployeeModal', () => {
  it('без активных заявок: причина обязательна, PATCH …/delete без reassign_to, закрытие после успеха', async () => {
    const user = userEvent.setup()
    const deletes = mockApi(0)
    const onClose = vi.fn()
    render(<DeleteEmployeeModal employee={emp()} onClose={onClose} />)

    expect(screen.getByText('Удаление сотрудника')).toBeInTheDocument()
    expect(screen.getByText('Удалить сотрудника Андрей Афанасьев?')).toBeInTheDocument()
    const del = screen.getByRole('button', { name: 'Удалить' })
    expect(del).toBeDisabled()

    await user.type(screen.getByPlaceholderText('Укажите причину'), 'Уволился')
    await waitFor(() => expect(del).toBeEnabled())
    await user.click(del)

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(deletes).toEqual([{ id: '1', body: { reason: 'Уволился' } }])
  })

  it('с активными заявками: шаг передачи, преемник обязателен, в тело уходит reassign_to', async () => {
    const user = userEvent.setup()
    const deletes = mockApi(3)
    const onClose = vi.fn()
    render(<DeleteEmployeeModal employee={emp()} onClose={onClose} />)

    await user.type(screen.getByPlaceholderText('Укажите причину'), 'Перевод')
    // счётчик активных заявок грузится асинхронно — ждём, пока шаг переключится
    await user.click(screen.getByRole('button', { name: 'Удалить' }))
    expect(await screen.findByText('Передать заявки')).toBeInTheDocument()
    expect(screen.getByText(/У сотрудника 3 активных заявок/)).toBeInTheDocument()
    expect(deletes).toHaveLength(0)

    const reassign = screen.getByRole('button', { name: 'Передать и удалить' })
    expect(reassign).toBeDisabled()
    // в списке только Борис: Вера заблокирована, сам Андрей исключён
    const boris = await screen.findByRole('button', { name: /Борис Петров/ })
    expect(screen.queryByRole('button', { name: /Вера Сидорова/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Андрей Афанасьев/ })).not.toBeInTheDocument()
    expect(boris).toHaveTextContent('На смене')

    await user.click(boris)
    expect(reassign).toBeEnabled()
    await user.click(reassign)

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(deletes).toEqual([{ id: '1', body: { reason: 'Перевод', reassign_to: 2 } }])
  })

  it('«Назад» возвращает к подтверждению с сохранённой причиной; «Отмена» закрывает', async () => {
    const user = userEvent.setup()
    mockApi(1)
    const onClose = vi.fn()
    render(<DeleteEmployeeModal employee={emp()} onClose={onClose} />)

    await user.type(screen.getByPlaceholderText('Укажите причину'), 'Причина')
    await user.click(screen.getByRole('button', { name: 'Удалить' }))
    await screen.findByText('Передать заявки')
    await user.click(screen.getByRole('button', { name: 'Назад' }))

    expect(screen.getByText('Удаление сотрудника')).toBeInTheDocument()
    expect((screen.getByPlaceholderText('Укажите причину') as HTMLTextAreaElement).value).toBe('Причина')
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
