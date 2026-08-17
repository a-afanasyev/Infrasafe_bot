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

    // Роль executor по умолчанию — специализация обязательна (см. тест ниже)
    await userEvent.click(screen.getByRole('button', { name: /⚡/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Создать приглашение' }))

    // Инвайт-токен появляется в блоке результата
    await waitFor(() =>
      expect(screen.getByDisplayValue('invite_v1:abc')).toBeInTheDocument(),
    )
    // Плейсхолдер-создающий эндпоинт НЕ вызывался — дублей быть не может
    expect(directCreateCalled).toBe(false)
  })

  it('executor без специализации: кнопка заблокирована, запрос не уходит', async () => {
    // Регресс profk 2026-08-17: модалка позволяла отправить executor с пустым
    // списком специализаций, API отвечал 500 (ValueError из InviteService), и
    // менеджер видел «не работает выдача приглашений» без объяснения.
    let inviteCalled = false
    server.use(
      http.post('*/api/v2/shifts/employees/invite', () => {
        inviteCalled = true
        return HttpResponse.json({
          token: 'invite_v1:abc',
          bot_link: 'https://t.me/profkbot',
          expires_at: '2026-07-09T00:00:00Z',
        })
      }),
    )

    render(<AddEmployeeModal open onClose={noop} />)

    const submit = screen.getByRole('button', { name: 'Создать приглашение' })
    expect(submit).toBeDisabled()

    await userEvent.click(submit)
    expect(inviteCalled).toBe(false)

    // Выбрали специализацию — кнопка разблокировалась
    await userEvent.click(screen.getByRole('button', { name: /⚡/ }))
    expect(screen.getByRole('button', { name: 'Создать приглашение' })).toBeEnabled()
  })

  it('manager: специализация не нужна, кнопка активна сразу', async () => {
    render(<AddEmployeeModal open onClose={noop} />)

    await userEvent.click(screen.getByRole('button', { name: 'Менеджер' }))
    expect(screen.getByRole('button', { name: 'Создать приглашение' })).toBeEnabled()
  })
})
