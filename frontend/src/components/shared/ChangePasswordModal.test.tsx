import { describe, it, expect, vi, afterEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '@/stores/authStore'
import ChangePasswordModal from './ChangePasswordModal'

const URL = '*/api/v2/auth/set-password'

describe('ChangePasswordModal', () => {
  afterEach(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })

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

  // ── AUD3-16: current-password proof-of-presence ──────────────────────

  it('hides current-password field for first-time set (no has_password)', () => {
    useAuthStore.setState({ user: { id: 1, roles: [], has_password: false }, isAuthenticated: true })
    render(<ChangePasswordModal open onClose={vi.fn()} />)
    expect(screen.queryByLabelText('Текущий пароль')).not.toBeInTheDocument()
  })

  it('shows current field and sends current_password when has_password', async () => {
    useAuthStore.setState({ user: { id: 1, roles: [], has_password: true }, isAuthenticated: true })
    let body: Record<string, unknown> | null = null
    server.use(http.post(URL, async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>
      return HttpResponse.json({ ok: true })
    }))
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<ChangePasswordModal open onClose={onClose} />)

    await user.type(screen.getByLabelText('Текущий пароль'), 'oldpass123')
    await user.type(screen.getByLabelText('Новый пароль'), 'newpassword1')
    await user.type(screen.getByLabelText('Подтверждение пароля'), 'newpassword1')
    await user.click(screen.getByRole('button', { name: 'Обновить пароль' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(body).toEqual({
      password: 'newpassword1',
      confirm_password: 'newpassword1',
      current_password: 'oldpass123',
    })
  })

  it('blocks submit when current is required but empty', async () => {
    useAuthStore.setState({ user: { id: 1, roles: [], has_password: true }, isAuthenticated: true })
    let called = false
    server.use(http.post(URL, () => { called = true; return HttpResponse.json({ ok: true }) }))
    const user = userEvent.setup()
    render(<ChangePasswordModal open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Новый пароль'), 'newpassword1')
    await user.type(screen.getByLabelText('Подтверждение пароля'), 'newpassword1')
    // Submit button is disabled while current is empty; assert it never fires.
    expect(screen.getByRole('button', { name: 'Обновить пароль' })).toBeDisabled()
    expect(called).toBe(false)
  })

  it('reveals current field when server returns current_password_required (stale flag)', async () => {
    // has_password flag is stale (false) but the server still requires it.
    useAuthStore.setState({ user: { id: 1, roles: [], has_password: false }, isAuthenticated: true })
    server.use(http.post(URL, () =>
      HttpResponse.json({ detail: 'current_password_required' }, { status: 400 }),
    ))
    const user = userEvent.setup()
    render(<ChangePasswordModal open onClose={vi.fn()} />)

    expect(screen.queryByLabelText('Текущий пароль')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Новый пароль'), 'newpassword1')
    await user.type(screen.getByLabelText('Подтверждение пароля'), 'newpassword1')
    await user.click(screen.getByRole('button', { name: 'Обновить пароль' }))

    // Field revealed + localized message shown.
    expect(await screen.findByLabelText('Текущий пароль')).toBeInTheDocument()
    expect(screen.getByText('Введите текущий пароль')).toBeInTheDocument()
  })

  it('shows localized message on current_password_invalid', async () => {
    useAuthStore.setState({ user: { id: 1, roles: [], has_password: true }, isAuthenticated: true })
    server.use(http.post(URL, () =>
      HttpResponse.json({ detail: 'current_password_invalid' }, { status: 400 }),
    ))
    const user = userEvent.setup()
    render(<ChangePasswordModal open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Текущий пароль'), 'wrongpass1')
    await user.type(screen.getByLabelText('Новый пароль'), 'newpassword1')
    await user.type(screen.getByLabelText('Подтверждение пароля'), 'newpassword1')
    await user.click(screen.getByRole('button', { name: 'Обновить пароль' }))

    expect(await screen.findByText('Неверный текущий пароль')).toBeInTheDocument()
  })
})
