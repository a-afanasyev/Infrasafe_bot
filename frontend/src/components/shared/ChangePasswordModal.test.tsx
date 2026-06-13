import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import ChangePasswordModal from './ChangePasswordModal'

const URL = '*/api/v2/auth/set-password'

describe('ChangePasswordModal', () => {
  it('blocks submit and shows error when passwords mismatch (no request)', async () => {
    let called = false
    server.use(http.post(URL, () => { called = true; return HttpResponse.json({ ok: true }) }))
    const user = userEvent.setup()
    render(<ChangePasswordModal open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Новый пароль'), 'longenough1')
    await user.type(screen.getByLabelText('Подтверждение пароля'), 'different22')
    await user.click(screen.getByRole('button', { name: 'Обновить пароль' }))

    expect(await screen.findByText('Пароли не совпадают')).toBeInTheDocument()
    expect(called).toBe(false)
  })

  it('blocks submit when password is too short', async () => {
    let called = false
    server.use(http.post(URL, () => { called = true; return HttpResponse.json({ ok: true }) }))
    const user = userEvent.setup()
    render(<ChangePasswordModal open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Новый пароль'), 'short')
    await user.type(screen.getByLabelText('Подтверждение пароля'), 'short')
    await user.click(screen.getByRole('button', { name: 'Обновить пароль' }))

    expect(await screen.findByText(/слишком короткий/)).toBeInTheDocument()
    expect(called).toBe(false)
  })

  it('posts and closes on success', async () => {
    let body: Record<string, unknown> | null = null
    server.use(http.post(URL, async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>
      return HttpResponse.json({ ok: true })
    }))
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<ChangePasswordModal open onClose={onClose} />)

    await user.type(screen.getByLabelText('Новый пароль'), 'newpassword1')
    await user.type(screen.getByLabelText('Подтверждение пароля'), 'newpassword1')
    await user.click(screen.getByRole('button', { name: 'Обновить пароль' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(body).toEqual({ password: 'newpassword1', confirm_password: 'newpassword1' })
  })

  it('surfaces server detail on 400', async () => {
    server.use(http.post(URL, () =>
      HttpResponse.json({ detail: 'Password too short (min 8)' }, { status: 400 }),
    ))
    const user = userEvent.setup()
    render(<ChangePasswordModal open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Новый пароль'), 'validpass12')
    await user.type(screen.getByLabelText('Подтверждение пароля'), 'validpass12')
    await user.click(screen.getByRole('button', { name: 'Обновить пароль' }))

    expect(await screen.findByText('Password too short (min 8)')).toBeInTheDocument()
  })
})
