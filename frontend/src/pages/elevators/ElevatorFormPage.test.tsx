import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router'
import { render as rtlRender } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider } from 'react-i18next'
import { MemoryRouter } from 'react-router'
import { toast } from 'sonner'
import { render, screen, testI18n, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import { ELEVATOR_CARD, ELEVATOR_DETAIL } from '../../test/fixtures/elevators'
import {
  EMPTY_ELEVATOR_FORM,
  copyPassportFrom,
  toPatchPayload,
  validateElevatorForm,
} from '../../utils/elevatorForm'
import ElevatorFormPage from './ElevatorFormPage'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

function mockAddresses() {
  server.use(
    http.get('*/api/v2/addresses/yards', () => HttpResponse.json([{ id: 3, name: 'Двор 3' }])),
    http.get('*/api/v2/addresses/yards/3/buildings', () =>
      HttpResponse.json([{ id: 12, address: 'ул. Мирзо-Улугбека, 12', yard_id: 3 }]),
    ),
  )
}

function renderCreate() {
  return render(
    <Routes>
      <Route path="/dashboard/elevators/new" element={<ElevatorFormPage />} />
      <Route path="/dashboard/elevators/:id" element={<div>detail-page</div>} />
    </Routes>,
    { routerEntries: ['/dashboard/elevators/new'] },
  )
}

beforeEach(() => {
  useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: false })
  vi.mocked(toast.info).mockClear()
})

describe('ElevatorFormPage (создание)', () => {
  it('обязательные поля валидируются на клиенте — POST не уходит', async () => {
    let posted = false
    mockAddresses()
    server.use(
      http.get('*/api/v2/elevators', () => HttpResponse.json({ items: [], total: 0 })),
      http.post('*/api/v2/elevators', () => {
        posted = true
        return HttpResponse.json(ELEVATOR_DETAIL, { status: 201 })
      }),
    )
    const user = userEvent.setup()
    renderCreate()
    await screen.findByRole('heading', { name: 'Новый лифт' })
    await user.click(screen.getByRole('button', { name: 'Создать' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Заполните обязательные поля')
    expect(posted).toBe(false)
  })

  it('заполненная форма шлёт ElevatorCreateIn и уводит на карточку', async () => {
    let body: Record<string, unknown> | null = null
    mockAddresses()
    server.use(
      http.get('*/api/v2/elevators', () => HttpResponse.json({ items: [], total: 0 })),
      http.post('*/api/v2/elevators', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...ELEVATOR_DETAIL, id: 99 }, { status: 201 })
      }),
    )
    const user = userEvent.setup()
    renderCreate()
    await screen.findByRole('heading', { name: 'Новый лифт' })
    await screen.findByRole('option', { name: 'Двор 3' })
    await user.selectOptions(screen.getByLabelText(/^Двор/), '3')
    await screen.findByRole('option', { name: 'ул. Мирзо-Улугбека, 12' })
    await user.selectOptions(screen.getByLabelText(/^Дом/), '12')
    await user.type(screen.getByLabelText(/^Подъезд/), '2')
    await user.type(screen.getByLabelText(/^Номер лифта/), '1')
    await user.type(screen.getByLabelText(/^Номер паспорта/), 'P-9')
    await user.type(screen.getByLabelText(/^Производитель/), 'KONE')
    await user.type(screen.getByLabelText(/^Серийный номер/), 'SN-9')
    await user.click(screen.getByRole('button', { name: 'Создать' }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({
      building_id: 12, entrance_number: 2, elevator_number: 1,
      passport_number: 'P-9', manufacturer: 'KONE', serial_number: 'SN-9',
      factory_number: null, is_public: true, publish_downtime_details: false,
    })
    expect(await screen.findByText('detail-page')).toBeInTheDocument()
  })

  it('«Скопировать предыдущий» заполняет паспортные поля, но не номер/серийник/паспорт/подъезд', async () => {
    mockAddresses()
    server.use(
      http.get('*/api/v2/elevators', () =>
        HttpResponse.json({ items: [{ ...ELEVATOR_CARD, id: 5 }, { ...ELEVATOR_CARD, id: 7 }], total: 2 }),
      ),
      http.get('*/api/v2/elevators/7', () => HttpResponse.json(ELEVATOR_DETAIL)),
    )
    const user = userEvent.setup()
    renderCreate()
    await screen.findByRole('heading', { name: 'Новый лифт' })
    await user.type(screen.getByLabelText(/^Номер лифта/), '3')
    const copyBtn = screen.getByRole('button', { name: /Скопировать предыдущий/ })
    await waitFor(() => expect(copyBtn).toBeEnabled())
    await user.click(copyBtn)
    await waitFor(() => expect(screen.getByLabelText(/^Производитель/)).toHaveValue('OTIS'))
    expect(screen.getByLabelText(/^Модель/)).toHaveValue('Gen2')
    expect(screen.getByLabelText(/^Номер договора/)).toHaveValue('C-42')
    expect(screen.getByLabelText(/^Двор/)).toHaveValue('3')
    // оператор вводит сам
    expect(screen.getByLabelText(/^Номер лифта/)).toHaveValue(3)
    expect(screen.getByLabelText(/^Серийный номер/)).toHaveValue('')
    expect(screen.getByLabelText(/^Номер паспорта/)).toHaveValue('')
    expect(screen.getByLabelText(/^Подъезд/)).toHaveValue(null)
  })
})

describe('ElevatorFormPage (правка): сид формы один раз', () => {
  function renderEditWithClient(qc: QueryClient) {
    return rtlRender(
      <QueryClientProvider client={qc}>
        <I18nextProvider i18n={testI18n}>
          <MemoryRouter initialEntries={['/dashboard/elevators/7/edit']}>
            <Routes>
              <Route path="/dashboard/elevators/:id/edit" element={<ElevatorFormPage />} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    )
  }

  it('рефетч с тем же version не затирает ввод; новый version — пересид + toast', async () => {
    let version = 3
    mockAddresses()
    server.use(
      http.get('*/api/v2/elevators/7', () => HttpResponse.json({ ...ELEVATOR_DETAIL, version })),
    )
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 }, mutations: { retry: false } },
    })
    const user = userEvent.setup()
    renderEditWithClient(qc)
    const manufacturer = await screen.findByLabelText(/^Производитель/)
    await waitFor(() => expect(manufacturer).toHaveValue('OTIS'))
    await user.clear(manufacturer)
    await user.type(manufacturer, 'KONE')

    // фоновый рефетч: тот же version → форма не тронута, предупреждения нет
    await qc.refetchQueries({ queryKey: ['elevator', 7] })
    await waitFor(() => expect(qc.getQueryState(['elevator', 7, 'ru'])?.dataUpdateCount).toBeGreaterThan(1))
    expect(screen.getByLabelText(/^Производитель/)).toHaveValue('KONE')
    expect(toast.info).not.toHaveBeenCalled()

    // кто-то сохранил карточку: version вырос → пересид + toast.info
    version = 4
    await qc.refetchQueries({ queryKey: ['elevator', 7] })
    await waitFor(() => expect(screen.getByLabelText(/^Производитель/)).toHaveValue('OTIS'))
    expect(toast.info).toHaveBeenCalledWith(testI18n.t('elevators.form.reloaded'))
  })
})

describe('ElevatorFormPage (правка)', () => {
  it('PATCH несёт expected_version из карточки', async () => {
    let body: Record<string, unknown> | null = null
    mockAddresses()
    server.use(
      http.get('*/api/v2/elevators', () => HttpResponse.json({ items: [], total: 0 })),
      http.get('*/api/v2/elevators/7', () => HttpResponse.json(ELEVATOR_DETAIL)),
      http.patch('*/api/v2/elevators/7', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...ELEVATOR_DETAIL, version: 4 })
      }),
    )
    const user = userEvent.setup()
    render(
      <Routes>
        <Route path="/dashboard/elevators/:id/edit" element={<ElevatorFormPage />} />
        <Route path="/dashboard/elevators/:id" element={<div>detail-page</div>} />
      </Routes>,
      { routerEntries: ['/dashboard/elevators/7/edit'] },
    )
    await screen.findByRole('heading', { name: /Редактирование лифта/ })
    await waitFor(() => expect(screen.getByLabelText(/^Производитель/)).toHaveValue('OTIS'))
    await user.clear(screen.getByLabelText(/^Производитель/))
    await user.type(screen.getByLabelText(/^Производитель/), 'KONE')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({ manufacturer: 'KONE', expected_version: 3, building_id: 12 })
    expect(await screen.findByText('detail-page')).toBeInTheDocument()
  })
})

describe('elevatorForm (чистые функции)', () => {
  it('validateElevatorForm: required → positiveInt → null', () => {
    expect(validateElevatorForm(EMPTY_ELEVATOR_FORM)).toBe('required')
    const filled = {
      ...EMPTY_ELEVATOR_FORM, yard_id: '3', building_id: '12', entrance_number: '0', elevator_number: '1',
      passport_number: 'P', manufacturer: 'M', serial_number: 'S',
    }
    expect(validateElevatorForm(filled)).toBe('positiveInt')
    expect(validateElevatorForm({ ...filled, entrance_number: '2' })).toBeNull()
  })

  it('validateElevatorForm: cert_act_url только http(s)', () => {
    const ok = {
      ...EMPTY_ELEVATOR_FORM, building_id: '12', entrance_number: '2', elevator_number: '1',
      passport_number: 'P', manufacturer: 'M', serial_number: 'S',
    }
    expect(validateElevatorForm({ ...ok, cert_act_url: 'https://example.org/act.pdf' })).toBeNull()
    expect(validateElevatorForm({ ...ok, cert_act_url: 'javascript:alert(1)' })).toBe('invalidUrl')
    expect(validateElevatorForm({ ...ok, cert_act_url: 'example.org/act.pdf' })).toBe('invalidUrl')
    expect(validateElevatorForm({ ...ok, cert_act_url: '   ' })).toBeNull()
  })

  it('copyPassportFrom не трогает номер/серийник/паспорт/подъезд', () => {
    const current = { ...EMPTY_ELEVATOR_FORM, elevator_number: '4', entrance_number: '1', serial_number: 'X', passport_number: 'Y' }
    const out = copyPassportFrom(current, ELEVATOR_DETAIL)
    expect(out.manufacturer).toBe('OTIS')
    expect(out.contract_number).toBe('C-42')
    expect(out.elevator_number).toBe('4')
    expect(out.entrance_number).toBe('1')
    expect(out.serial_number).toBe('X')
    expect(out.passport_number).toBe('Y')
    expect(current.manufacturer).toBe('') // исходник не мутирован
  })

  it('toPatchPayload: пустые строки → null, числа → number', () => {
    const p = toPatchPayload(
      { ...EMPTY_ELEVATOR_FORM, building_id: '12', entrance_number: '2', elevator_number: '1', passport_number: 'P', manufacturer: 'M', serial_number: 'S', production_year: '2015' },
      3,
    )
    expect(p.expected_version).toBe(3)
    expect(p.production_year).toBe(2015)
    expect(p.model).toBeNull()
    expect(p.contract_until).toBeNull()
  })
})
