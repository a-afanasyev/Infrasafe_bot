import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../test/test-utils'
import { server } from '../test/msw/server'
import { useAuthStore } from '../stores/authStore'
import LoginPage from './LoginPage'

// TEST-068 Phase 5: страница входа (password + MFA-OTP флоу). publicClient бьёт
// /auth/login; authStore.login() подтягивает /profile. MSW per-test.

beforeEach(() => {
  sessionStorage.clear()
  useAuthStore.setState({ user: null, isAuthenticated: false, hydrating: false })
})

function emailInput() {
  return document.querySelector('input[type="email"]') as HTMLInputElement
}
function passwordInput() {
  return document.querySelector('input[type="password"]') as HTMLInputElement
}

describe('LoginPage', () => {
  it('renders email/password fields and the submit button', () => {
    render(<LoginPage />)
    expect(emailInput()).not.toBeNull()
    expect(passwordInput()).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Войти' })).toBeInTheDocument()
  })

  it('logs in without MFA and marks the session authenticated', async () => {
    server.use(
      http.post('*/api/v2/auth/login', () => HttpResponse.json({ mfa_required: false })),
      http.get('*/api/v2/profile', () => HttpResponse.json({ id: 1, roles: ['manager'], first_name: 'M' })),
    )
    const user = userEvent.setup()
    render(<LoginPage />)
    await user.type(emailInput(), 'admin@example.com')
    await user.type(passwordInput(), 'secret')
    await user.click(screen.getByRole('button', { name: 'Войти' }))
    await waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(true))
    expect(useAuthStore.getState().user).toEqual({ id: 1, roles: ['manager'], first_name: 'M' })
  })

  it('switches to the OTP form when MFA is required', async () => {
    server.use(
      http.post('*/api/v2/auth/login', () =>
        HttpResponse.json({ mfa_required: true, mfa_token: 'tok-123' }),
      ),
    )
    const user = userEvent.setup()
    render(<LoginPage />)
    await user.type(emailInput(), 'admin@example.com')
    await user.type(passwordInput(), 'secret')
    await user.click(screen.getByRole('button', { name: 'Войти' }))
    // OTP-форма: код отправлен в Telegram + поле для 6-значного кода.
    expect(await screen.findByText('Код отправлен в Telegram')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('000000')).toBeInTheDocument()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })

  it('shows the server detail on invalid credentials', async () => {
    server.use(
      http.post('*/api/v2/auth/login', () =>
        HttpResponse.json({ detail: 'Неверные учётные данные' }, { status: 401 }),
      ),
    )
    const user = userEvent.setup()
    render(<LoginPage />)
    await user.type(emailInput(), 'admin@example.com')
    await user.type(passwordInput(), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Войти' }))
    expect(await screen.findByText('Неверные учётные данные')).toBeInTheDocument()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})
