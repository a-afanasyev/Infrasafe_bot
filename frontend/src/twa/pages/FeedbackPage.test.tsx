import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'

// src/twa/** исключён из coverage, но импорт useTelegramSDK всё равно
// исполняется — мокаем, чтобы не трогать реальный Telegram-рантайм.
vi.mock('../hooks/useTelegramSDK', () => ({
  useTelegramSDK: () => ({ haptic: vi.fn(), showBackButton: () => () => {} }),
}))

import FeedbackPage from './FeedbackPage'

describe('TWA FeedbackPage', () => {
  beforeEach(() => server.resetHandlers())

  it('renders type options and disables submit until valid', () => {
    render(<FeedbackPage />)
    expect(screen.getByText('Жалоба')).toBeInTheDocument()
    expect(screen.getByText('Пожелание')).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: 'Отправить' })
    expect(submit).toBeDisabled()
  })

  it('keeps submit disabled when text is too short even after picking type', async () => {
    const user = userEvent.setup()
    render(<FeedbackPage />)
    await user.click(screen.getByText('Жалоба'))
    await user.type(screen.getByRole('textbox'), 'коротко')
    expect(screen.getByRole('button', { name: 'Отправить' })).toBeDisabled()
  })

  it('submits type + text to POST /api/v2/feedback', async () => {
    const user = userEvent.setup()
    let captured: { type: unknown; text: unknown } | null = null
    server.use(
      http.post('*/api/v2/feedback', async ({ request }) => {
        const fd = await request.formData()
        captured = { type: fd.get('type'), text: fd.get('text') }
        return HttpResponse.json({ id: 1, type: 'complaint', status: 'new' })
      }),
    )

    render(<FeedbackPage />)
    await user.click(screen.getByText('Жалоба'))
    await user.type(screen.getByRole('textbox'), 'Лифт не работает уже неделю')

    const submit = screen.getByRole('button', { name: 'Отправить' })
    expect(submit).toBeEnabled()
    await user.click(submit)

    await waitFor(() => expect(captured).not.toBeNull())
    expect(captured!.type).toBe('complaint')
    expect(captured!.text).toBe('Лифт не работает уже неделю')
  })
})
