import { describe, it, expect, afterEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import CallCenterModal from './CallCenterModal'

// Форма колл-центра для категории «Лифт» (Ф4a-3): дом из справочника →
// building_id, лифт дома (for-building), «работает?»; свободный адрес скрыт.

const BUILDINGS = [
  { id: 12, address: 'ул. Мирзо-Улугбека, 12', yard_id: 3, yard_name: 'Двор 3', entrance_count: 4, floor_count: 9, description: null, gps_latitude: null, gps_longitude: null, is_active: true },
]
const ELEVATORS = [
  { id: 7, entrance_number: 2, elevator_number: 1, label: 'Лифт 1, подъезд 2', current_status: 'working' },
  { id: 8, entrance_number: 3, elevator_number: 1, label: 'Лифт 1, подъезд 3', current_status: 'not_working' },
]

function mockDirectories() {
  server.use(
    http.get('*/api/v2/addresses/buildings', () => HttpResponse.json(BUILDINGS)),
    http.get('*/api/v2/elevators/for-building/12', () => HttpResponse.json(ELEVATORS)),
  )
}

async function fillBase(user: ReturnType<typeof userEvent.setup>, category: string) {
  await user.selectOptions(screen.getByLabelText('Категория'), category)
  await user.type(screen.getByLabelText('Описание проблемы'), 'Не едет')
}

afterEach(() => vi.unstubAllEnvs())

describe('CallCenterModal — категория «Лифт»', () => {
  it('флаг включён: дом/лифт/работает вместо адреса; body с building_id и полями лифта', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockDirectories()
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/callcenter/requests', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ request_number: '260906-001' }, { status: 201 })
      }),
    )
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<CallCenterModal isOpen onClose={onClose} />)

    await fillBase(user, 'elevator')
    expect(screen.queryByLabelText('Адрес / квартира *')).toBeNull()

    const submit = screen.getByRole('button', { name: 'Создать заявку' })
    expect(submit).toBeDisabled()

    await screen.findByRole('option', { name: 'ул. Мирзо-Улугбека, 12' })
    await user.selectOptions(screen.getByLabelText('Дом *'), '12')
    await screen.findByRole('option', { name: 'Лифт 1, подъезд 3 — Не работает' })
    await user.selectOptions(screen.getByLabelText('Лифт *'), '8')
    expect(submit).toBeDisabled()
    await user.click(screen.getByLabelText('Нет'))
    expect(submit).toBeEnabled()

    await user.click(submit)
    await waitFor(() =>
      expect(body).toEqual({
        category: 'elevator',
        urgency: 'low',
        description: 'Не едет',
        building_id: 12,
        elevator_id: 8,
        elevator_operational: false,
      }),
    )
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('смена дома сбрасывает выбранный лифт', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockDirectories()
    server.use(http.get('*/api/v2/elevators/for-building/13', () => HttpResponse.json([])))
    const user = userEvent.setup()
    render(<CallCenterModal isOpen onClose={() => {}} />)
    await fillBase(user, 'elevator')
    await screen.findByRole('option', { name: 'ул. Мирзо-Улугбека, 12' })
    await user.selectOptions(screen.getByLabelText('Дом *'), '12')
    await screen.findByRole('option', { name: 'Лифт 1, подъезд 2 — Работает' })
    await user.selectOptions(screen.getByLabelText('Лифт *'), '7')
    await user.click(screen.getByLabelText('Да'))
    expect(screen.getByRole('button', { name: 'Создать заявку' })).toBeEnabled()

    await user.selectOptions(screen.getByLabelText('Дом *'), '')
    expect(screen.getByLabelText<HTMLSelectElement>('Лифт *').value).toBe('')
    expect(screen.getByRole('button', { name: 'Создать заявку' })).toBeDisabled()
  })

  it('флаг выключен: форма как раньше — свободный адрес, полей лифта нет', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'false')
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/v2/callcenter/requests', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ request_number: '260906-002' }, { status: 201 })
      }),
    )
    const user = userEvent.setup()
    render(<CallCenterModal isOpen onClose={() => {}} />)
    await fillBase(user, 'elevator')
    expect(screen.queryByLabelText('Дом *')).toBeNull()
    await user.type(screen.getByLabelText('Адрес / квартира *'), 'ул. Тестовая, 1')
    await user.click(screen.getByRole('button', { name: 'Создать заявку' }))
    await waitFor(() =>
      expect(body).toEqual({ category: 'elevator', urgency: 'low', description: 'Не едет', address: 'ул. Тестовая, 1' }),
    )
  })

  it('обычная категория при включённом флаге — свободный адрес', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    const user = userEvent.setup()
    render(<CallCenterModal isOpen onClose={() => {}} />)
    await fillBase(user, 'plumbing')
    expect(screen.getByLabelText('Адрес / квартира *')).toBeInTheDocument()
    expect(screen.queryByLabelText('Дом *')).toBeNull()
  })

  it('422 от сервера показывается текстом ошибки', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    mockDirectories()
    server.use(
      http.post('*/api/v2/callcenter/requests', () =>
        HttpResponse.json({ detail: 'elevator does not belong to building' }, { status: 422 })),
    )
    const user = userEvent.setup()
    render(<CallCenterModal isOpen onClose={() => {}} />)
    await fillBase(user, 'elevator')
    await screen.findByRole('option', { name: 'ул. Мирзо-Улугбека, 12' })
    await user.selectOptions(screen.getByLabelText('Дом *'), '12')
    await screen.findByRole('option', { name: 'Лифт 1, подъезд 2 — Работает' })
    await user.selectOptions(screen.getByLabelText('Лифт *'), '7')
    await user.click(screen.getByLabelText('Да'))
    await user.click(screen.getByRole('button', { name: 'Создать заявку' }))
    expect(await screen.findByText('elevator does not belong to building')).toBeInTheDocument()
  })
})
