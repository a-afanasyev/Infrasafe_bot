import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import CreateTemplateModal from './CreateTemplateModal'

function noop() {}

describe('CreateTemplateModal — recurrence mode', () => {
  it('shows weekday grid by default and hides cycle inputs', () => {
    render(<CreateTemplateModal isOpen onClose={noop} />)
    // weekday grid is rendered via the days-of-week label
    expect(screen.getByText('Дни недели')).toBeInTheDocument()
    // cycle inputs are not present
    expect(screen.queryByText('Рабочих дней')).not.toBeInTheDocument()
    expect(screen.queryByText('Первый рабочий день')).not.toBeInTheDocument()
  })

  it('switches to cycle mode: shows cycle inputs and hides weekday grid', async () => {
    const user = userEvent.setup()
    render(<CreateTemplateModal isOpen onClose={noop} />)
    await user.click(screen.getByRole('button', { name: 'Цикл' }))
    expect(screen.getByText('Рабочих дней')).toBeInTheDocument()
    expect(screen.getByText('Выходных дней')).toBeInTheDocument()
    expect(screen.getByText('Первый рабочий день')).toBeInTheDocument()
    // weekday grid label gone
    expect(screen.queryByText('Дни недели')).not.toBeInTheDocument()
  })

  it('sends cycle fields in the create payload', async () => {
    let posted: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/shifts/templates', async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 1 })
      }),
    )
    const user = userEvent.setup()
    render(<CreateTemplateModal isOpen onClose={noop} />)

    await user.type(screen.getByPlaceholderText('Например: Дневная смена'), 'Сутки через трое')
    await user.click(screen.getByRole('button', { name: 'Цикл' }))
    // apply 1/3 preset
    await user.click(screen.getByRole('button', { name: '1/3' }))
    // anchor date is required by client-side validation
    const anchorInput = document.querySelector('input[type="date"]') as HTMLInputElement
    await user.type(anchorInput, '2026-06-01')

    await user.click(screen.getByRole('button', { name: 'Создать шаблон' }))

    await waitFor(() => expect(posted).not.toBeNull())
    expect(posted).toMatchObject({
      name: 'Сутки через трое',
      recurrence_mode: 'cycle',
      cycle_days_on: 1,
      cycle_days_off: 3,
      cycle_anchor_date: '2026-06-01',
    })
    // weekday list should not be sent in cycle mode
    expect(posted).not.toHaveProperty('days_of_week')
  })

  it('blocks cycle submit with empty anchor date and shows a validation error', async () => {
    let posted: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/shifts/templates', async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 3 })
      }),
    )
    const user = userEvent.setup()
    render(<CreateTemplateModal isOpen onClose={noop} />)

    await user.type(screen.getByPlaceholderText('Например: Дневная смена'), 'Без даты')
    await user.click(screen.getByRole('button', { name: 'Цикл' }))
    // leave anchor date empty
    await user.click(screen.getByRole('button', { name: 'Создать шаблон' }))

    expect(await screen.findByText('Укажите первый рабочий день цикла')).toBeInTheDocument()
    expect(posted).toBeNull()
  })

  it('sends weekday fields (no cycle) in the default payload', async () => {
    let posted: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/shifts/templates', async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ id: 2 })
      }),
    )
    const user = userEvent.setup()
    render(<CreateTemplateModal isOpen onClose={noop} />)

    await user.type(screen.getByPlaceholderText('Например: Дневная смена'), 'Будни')
    await user.click(screen.getByRole('button', { name: 'Создать шаблон' }))

    await waitFor(() => expect(posted).not.toBeNull())
    expect(posted).toMatchObject({
      name: 'Будни',
      recurrence_mode: 'weekday',
    })
    expect(posted).toHaveProperty('days_of_week')
    expect(posted).not.toHaveProperty('cycle_days_on')
  })
})
