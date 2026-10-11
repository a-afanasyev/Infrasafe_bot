import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import RolesSection from './RolesSection'

const BASE = '*/api/v2/shifts/employees'
const ROLES = [
  { key: 'executor', title: 'Исполнитель', is_system: true, actions: [], customized: [], users_count: 1 },
  { key: 'security_operator', title: 'Оператор охраны', is_system: true, actions: [], customized: [], users_count: 0 },
  { key: 'senior_exec', title: 'Старший исполнитель', is_system: false, actions: [], customized: [], users_count: 0 },
]

let lastExpected: string[] | undefined

function mockApi(canEdit: boolean, onPut?: (roles: string[]) => void) {
  server.use(
    http.get(`${BASE}/rbac/roles`, () => HttpResponse.json({ roles: ROLES, can_edit: canEdit })),
    http.get(`${BASE}/7/roles`, () =>
      HttpResponse.json({ user_id: 7, roles: ['executor'], active_role: 'executor', is_superadmin: false, can_edit: canEdit })),
    http.put(`${BASE}/7/roles`, async ({ request }) => {
      const body = (await request.json()) as { roles: string[]; expected?: string[] }
      lastExpected = body.expected
      onPut?.(body.roles)
      return HttpResponse.json({ user_id: 7, roles: body.roles, active_role: body.roles[0], is_superadmin: false, can_edit: true })
    }),
  )
}

describe('RolesSection', () => {
  it('manager sees roles but cannot change them', async () => {
    mockApi(false)
    render(<RolesSection employeeId={7} />)
    const box = await screen.findByRole('checkbox', { name: 'Исполнитель' })
    expect(box).toBeChecked()
    expect(box).toBeDisabled()
    expect(screen.getByText('Менять роли может только суперадмин.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Сохранить' })).toBeNull()
  })

  it('superadmin grants a role and saves the full set', async () => {
    let sent: string[] | null = null
    mockApi(true, (roles) => { sent = roles })
    const user = userEvent.setup()
    render(<RolesSection employeeId={7} />)
    await user.click(await screen.findByRole('checkbox', { name: 'Оператор охраны' }))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(sent).toEqual(['executor', 'security_operator']))
    // какие роли видел редактор — сервер ответит 409, если их уже поменяли
    expect(lastExpected).toEqual(['executor'])
  })
  it('custom role needs a system role and goes after it', async () => {
    let sent: string[] | null = null
    mockApi(true, (roles) => { sent = roles })
    const user = userEvent.setup()
    render(<RolesSection employeeId={7} />)
    await user.click(await screen.findByRole('checkbox', { name: 'Старший исполнитель' }))
    await user.click(screen.getByRole('checkbox', { name: 'Исполнитель' }))
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeDisabled()
    expect(screen.getByText(/Нужна хотя бы одна системная роль/)).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Исполнитель' }))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(sent).toEqual(['executor', 'senior_exec']))
  })
})
