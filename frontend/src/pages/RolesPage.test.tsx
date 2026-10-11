import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '../test/test-utils'
import { server } from '../test/msw/server'
import RolesPage from './RolesPage'

const BASE = '*/api/v2/shifts/employees/rbac'

const CATALOG = [
  { key: 'staff.manage', title: 'Сотрудники', area: 'staff', approved_only: false, superadmin_only: false, default_roles: ['manager'] },
  { key: 'requests.stats', title: 'Статистика заявок', area: 'requests', approved_only: false, superadmin_only: false, default_roles: ['manager'] },
  { key: 'rbac.manage', title: 'Роли: изменение', area: 'rbac', approved_only: false, superadmin_only: true, default_roles: [] },
]

const ROLES = [
  { key: 'manager', title: 'Менеджер', description: null, is_system: true, actions: ['requests.stats', 'staff.manage'], customized: [], users_count: 3 },
  { key: 'senior_exec', title: 'Старший исполнитель', description: null, is_system: false, actions: [], customized: [], users_count: 0 },
]

function mockApi(canEdit: boolean, onPut?: (body: unknown) => void) {
  server.use(
    http.get(`${BASE}/catalog`, () => HttpResponse.json(CATALOG)),
    http.get(`${BASE}/roles`, () => HttpResponse.json({ roles: ROLES, can_edit: canEdit })),
    http.put(`${BASE}/roles/:key`, async ({ request, params }) => {
      const body = await request.json()
      onPut?.(body)
      return HttpResponse.json({ ...ROLES[0], key: params.key, ...(body as object) })
    }),
  )
}

describe('RolesPage', () => {
  it('manager sees roles read-only: no save, checkboxes disabled', async () => {
    mockApi(false)
    render(<RolesPage />)
    expect(await screen.findByText(/Только просмотр/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Сохранить' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Новая роль' })).toBeNull()
    const box = screen.getByRole('checkbox', { name: /Сотрудники/ })
    expect(box).toBeChecked()
    expect(box).toBeDisabled()
  })

  it('never offers superadmin-only actions for a role', async () => {
    mockApi(true)
    render(<RolesPage />)
    await screen.findByRole('checkbox', { name: /Сотрудники/ })
    expect(screen.queryByText('Роли: изменение')).toBeNull()
  })

  it('superadmin unchecks an action and saves the full set', async () => {
    let sent: { actions?: string[] } | null = null
    mockApi(true, (body) => { sent = body as { actions?: string[] } })
    const user = userEvent.setup()
    render(<RolesPage />)
    await user.click(await screen.findByRole('checkbox', { name: /Статистика заявок/ }))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(sent).not.toBeNull())
    expect(sent!.actions).toEqual(['staff.manage'])
  })

  it('lists custom roles with their badge and user counts', async () => {
    mockApi(true)
    render(<RolesPage />)
    const list = await screen.findByRole('list', { name: 'Список ролей' })
    expect(within(list).getByText('Старший исполнитель')).toBeInTheDocument()
    expect(within(list).getByText('своя')).toBeInTheDocument()
    expect(within(list).getByText('3 сотрудника')).toBeInTheDocument()
  })

  it('shows translated area names, not codes', async () => {
    mockApi(true)
    render(<RolesPage />)
    expect(await screen.findByText('Персонал и смены')).toBeInTheDocument()
    expect(screen.getByText('Заявки')).toBeInTheDocument()
    expect(screen.queryByText('staff')).toBeNull()
  })

  it('cancel drops unsaved changes', async () => {
    mockApi(true)
    const user = userEvent.setup()
    render(<RolesPage />)
    const box = await screen.findByRole('checkbox', { name: /Статистика заявок/ })
    await user.click(box)
    expect(box).not.toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(screen.getByRole('checkbox', { name: /Статистика заявок/ })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeDisabled()
  })

  it('switching roles with unsaved changes asks first', async () => {
    mockApi(true)
    const user = userEvent.setup()
    render(<RolesPage />)
    await user.click(await screen.findByRole('checkbox', { name: /Статистика заявок/ }))
    const list = screen.getByRole('list', { name: 'Список ролей' })
    await user.click(within(list).getByText('Старший исполнитель'))
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('несохранённые изменения')
    // «Остаться» — правка на месте
    await user.click(within(alert).getByRole('button', { name: 'Остаться' }))
    expect(screen.getByRole('checkbox', { name: /Статистика заявок/ })).not.toBeChecked()
    // «Отбросить и перейти» — открыта другая роль
    await user.click(within(list).getByText('Старший исполнитель'))
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Отбросить и перейти' }))
    expect(screen.getByDisplayValue('Старший исполнитель')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
