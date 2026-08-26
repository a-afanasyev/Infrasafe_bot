import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import CreateShiftFromTemplateModal from './CreateShiftFromTemplateModal'

function noop() {}

const EMPLOYEES = [
  { id: 7, first_name: 'Иван', last_name: 'Петров', phone: null, specialization: ['electrician'], active_shift_id: null, verification_status: 'approved', status: 'approved', roles: ['executor'] },
  { id: 9, first_name: 'Олег', last_name: 'Смирнов', phone: null, specialization: ['plumber'], active_shift_id: 4, verification_status: 'approved', status: 'approved', roles: ['executor'] },
]

function mockEmployees() {
  const seenUrls: string[] = []
  server.use(http.get('*/api/v2/shifts/employees', ({ request }) => {
    seenUrls.push(request.url)
    return HttpResponse.json(EMPLOYEES)
  }))
  return seenUrls
}

describe('CreateShiftFromTemplateModal', () => {
  it('renders date picker and the executor checkbox list', async () => {
    mockEmployees()
    render(<CreateShiftFromTemplateModal isOpen onClose={noop} templateId={5} templateName="Дневная электрика" />)
    expect(screen.getByText('Дата смены')).toBeInTheDocument()
    expect(await screen.findByText('Иван Петров')).toBeInTheDocument()
    expect(screen.getByText('Олег Смирнов')).toBeInTheDocument()
    // Список — чекбоксы, а не кнопки-плитки (исходный дефект UX).
    expect(screen.getAllByRole('checkbox')).toHaveLength(2)
  })

  it('запрашивает сотрудников ПОД специализации шаблона (for_specializations)', async () => {
    // Фильтр «кто подходит шаблону» живёт на сервере (канон-предикат);
    // забытый параметр вернул бы весь список — регресс исходного дефекта.
    const seenUrls = mockEmployees()
    render(
      <CreateShiftFromTemplateModal
        isOpen onClose={noop} templateId={5}
        requiredSpecializations={['landscaping', 'cleaning']}
      />,
    )
    await screen.findByText('Иван Петров')
    expect(seenUrls.length).toBeGreaterThan(0)
    expect(new URL(seenUrls[0]).searchParams.get('for_specializations'))
      .toBe('landscaping,cleaning')
    // Подпись объясняет, почему список короче полного.
    expect(screen.getByText(/Показаны только специалисты/)).toBeInTheDocument()
  })

  it('шаблон без специализаций — параметр не шлётся, подписи нет', async () => {
    const seenUrls = mockEmployees()
    render(<CreateShiftFromTemplateModal isOpen onClose={noop} templateId={5} requiredSpecializations={[]} />)
    await screen.findByText('Иван Петров')
    expect(new URL(seenUrls[0]).searchParams.get('for_specializations')).toBeNull()
    expect(screen.queryByText(/Показаны только специалисты/)).not.toBeInTheDocument()
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
    await screen.findByText('Иван Петров')
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
    await user.click(await screen.findByText('Иван Петров'))
    await user.click(screen.getByRole('button', { name: 'Создать смену' }))

    await waitFor(() => expect(posted).not.toBeNull())
    expect(posted).toMatchObject({ template_id: 5, user_ids: [7] })
    expect(typeof (posted as Record<string, unknown>).date).toBe('string')
  })

  it('счётчик выбранных обновляется по кликам', async () => {
    mockEmployees()
    const user = userEvent.setup()
    render(<CreateShiftFromTemplateModal isOpen onClose={noop} templateId={5} />)
    await user.click(await screen.findByText('Иван Петров'))
    await user.click(screen.getByText('Олег Смирнов'))
    expect(screen.getByText('Выбрано: 2')).toBeInTheDocument()
  })
})
