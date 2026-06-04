import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import CreateShiftFromTemplateModal from './CreateShiftFromTemplateModal'

function noop() {}

const EMPLOYEES = [
  { id: 7, first_name: 'Иван', last_name: 'Петров', phone: null, specialization: ['electrician'], active_shift_id: null, verification_status: 'approved', status: 'approved' },
  { id: 9, first_name: 'Олег', last_name: 'Смирнов', phone: null, specialization: ['plumber'], active_shift_id: null, verification_status: 'approved', status: 'approved' },
]

function mockEmployees() {
  server.use(http.get('*/api/v2/shifts/employees', () => HttpResponse.json(EMPLOYEES)))
}

describe('CreateShiftFromTemplateModal', () => {
  it('renders date picker and the executor list', async () => {
    mockEmployees()
    render(<CreateShiftFromTemplateModal isOpen onClose={noop} templateId={5} templateName="Дневная электрика" />)
    expect(screen.getByText('Дата смены')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Иван Петров' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Олег Смирнов' })).toBeInTheDocument()
  })

  it('blocks submit with no executor selected and does not POST', async () => {
    mockEmployees()
    let posted: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/shifts/from-template', async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>
        return HttpResponse.json([{ id: 1 }])
      }),
    )
    const user = userEvent.setup()
    render(<CreateShiftFromTemplateModal isOpen onClose={noop} templateId={5} />)
    await screen.findByRole('button', { name: 'Иван Петров' })
    await user.click(screen.getByRole('button', { name: 'Создать смену' }))
    expect(await screen.findByText('Выберите хотя бы одного исполнителя')).toBeInTheDocument()
    expect(posted).toBeNull()
  })

  it('posts template_id, date and selected user_ids on submit', async () => {
    mockEmployees()
    let posted: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/shifts/from-template', async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>
        return HttpResponse.json([{ id: 1 }])
      }),
    )
    const user = userEvent.setup()
    render(<CreateShiftFromTemplateModal isOpen onClose={noop} templateId={5} />)
    await user.click(await screen.findByRole('button', { name: 'Иван Петров' }))
    await user.click(screen.getByRole('button', { name: 'Создать смену' }))

    await waitFor(() => expect(posted).not.toBeNull())
    expect(posted).toMatchObject({ template_id: 5, user_ids: [7] })
    expect(typeof (posted as Record<string, unknown>).date).toBe('string')
  })
})
