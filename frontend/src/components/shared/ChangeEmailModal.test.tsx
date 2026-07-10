import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import ChangeEmailModal from './ChangeEmailModal'

const PROFILE = '*/api/v2/profile'

function profileHandler(email: string | null) {
  return http.get(PROFILE, () => HttpResponse.json({ id: 1, telegram_id: 1, email }))
}

describe('ChangeEmailModal', () => {
  it('prefills the current email from the profile', async () => {
    server.use(profileHandler('old@example.com'))
    render(<ChangeEmailModal open onClose={vi.fn()} />)

    await waitFor(() =>
      expect(screen.getByLabelText('Email')).toHaveValue('old@example.com'),
    )
  })

  it('blocks submit and shows error on invalid email (no request)', async () => {
    server.use(profileHandler(null))
    let called = false
    server.use(http.patch(PROFILE, () => { called = true; return HttpResponse.json({ ok: true }) }))
    const user = userEvent.setup()
    render(<ChangeEmailModal open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.click(screen.getByRole('button', { name: 'Сохранить email' }))

    expect(await screen.findByText('Введите корректный email')).toBeInTheDocument()
    expect(called).toBe(false)
  })

  it('patches and closes on success', async () => {
    server.use(profileHandler('old@example.com'))
    let body: Record<string, unknown> | null = null
    server.use(http.patch(PROFILE, async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>
      return HttpResponse.json({ ok: true })
    }))
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<ChangeEmailModal open onClose={onClose} />)

    const input = await screen.findByLabelText('Email')
    await waitFor(() => expect(input).toHaveValue('old@example.com'))
    await user.clear(input)
    await user.type(input, 'new@example.com')
    await user.click(screen.getByRole('button', { name: 'Сохранить email' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(body).toEqual({ email: 'new@example.com' })
  })

  it('surfaces string server detail on error', async () => {
    server.use(profileHandler(null))
    server.use(http.patch(PROFILE, () =>
      HttpResponse.json({ detail: 'email already in use' }, { status: 400 }),
    ))
    const user = userEvent.setup()
    render(<ChangeEmailModal open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Email'), 'taken@example.com')
    await user.click(screen.getByRole('button', { name: 'Сохранить email' }))

    expect(await screen.findByText('email already in use')).toBeInTheDocument()
  })

  it('falls back to generic message when server detail is a pydantic list (422)', async () => {
    server.use(profileHandler(null))
    server.use(http.patch(PROFILE, () =>
      HttpResponse.json({ detail: [{ loc: ['body', 'email'], msg: 'value is not a valid email address' }] }, { status: 422 }),
    ))
    const user = userEvent.setup()
    render(<ChangeEmailModal open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Email'), 'a@b.co')
    await user.click(screen.getByRole('button', { name: 'Сохранить email' }))

    expect(await screen.findByText('Введите корректный email')).toBeInTheDocument()
  })
})
