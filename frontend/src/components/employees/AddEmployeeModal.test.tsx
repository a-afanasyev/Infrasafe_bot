import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import AddEmployeeModal from './AddEmployeeModal'

function noop() {}

describe('AddEmployeeModal — invite-only', () => {
  it('submits ONLY the invite endpoint, never POST /employees (no placeholder dupes)', async () => {
    let directCreateCalled = false
    server.use(
      http.post('*/api/v2/shifts/employees/invite', () =>
        HttpResponse.json({
          token: 'invite_v1:abc',
          bot_link: 'https://t.me/profkbot',
          expires_at: '2026-07-09T00:00:00Z',
        }),
      ),
      http.post('*/api/v2/shifts/employees', () => {
        directCreateCalled = true
        return HttpResponse.json({ id: 1 }, { status: 201 })
      }),
    )

    render(<AddEmployeeModal open onClose={noop} />)
    expect(screen.getByText('Пригласить сотрудника')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Создать приглашение' }))

    // Инвайт-токен появляется в блоке результата
    await waitFor(() =>
      expect(screen.getByDisplayValue('invite_v1:abc')).toBeInTheDocument(),
    )
    // Плейсхолдер-создающий эндпоинт НЕ вызывался — дублей быть не может
    expect(directCreateCalled).toBe(false)
  })
})
