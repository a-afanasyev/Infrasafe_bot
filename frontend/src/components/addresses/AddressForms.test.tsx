import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import type { BuildingBrief, YardBrief } from '../../types/api'
import YardFormModal from './YardFormModal'
import BuildingFormModal from './BuildingFormModal'
import AddObjectModal from './AddObjectModal'
import BulkCreateModal from './BulkCreateModal'

// TEST-068 (порция addresses): формы двора/здания, единая модалка «Новый объект»
// и массовое создание квартир — тела запросов, валидация GPS, диапазоны номеров.

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const YARDS: YardBrief[] = [
  { id: 1, name: 'Двор 1', description: null, gps_latitude: null, gps_longitude: null, is_active: true, created_at: null, buildings_count: 0 },
  { id: 2, name: 'Двор 2', description: null, gps_latitude: null, gps_longitude: null, is_active: true, created_at: null, buildings_count: 0 },
]
const BUILDING: BuildingBrief = {
  id: 10, address: 'ул. Тестовая, 5', yard_id: 2, yard_name: 'Двор 2', entrance_count: 3, floor_count: 9,
  description: 'Панель', gps_latitude: 41.3, gps_longitude: 69.2, is_active: true, created_at: null, apartments_count: 0,
}


/** Label в этих модалках не связан с полем атрибутом for — берём контрол из того же блока. */
function byLabel(text: string): HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement {
  const label = screen.getByText(text)
  const control = label.parentElement?.querySelector('input, select, textarea')
  if (!control) throw new Error(`нет поля рядом с подписью «${text}»`)
  return control as HTMLInputElement
}

function capture(method: 'post' | 'patch', path: string, status = 200, body: unknown = {}) {
  const calls: { url: string; body: unknown }[] = []
  server.use(http[method](`*/api/v2/addresses/${path}`, async ({ request }) => {
    calls.push({ url: new URL(request.url).pathname, body: await request.json() })
    return HttpResponse.json(body, { status })
  }))
  return calls
}

describe('YardFormModal', () => {
  it('создание: имя обязательно, POST /yards с trim/null/is_active; закрытие после успеха', async () => {
    const user = userEvent.setup()
    const calls = capture('post', 'yards', 201, YARDS[0])
    const onClose = vi.fn()
    render(<YardFormModal onClose={onClose} />)
    expect(screen.getByText('Новый двор')).toBeInTheDocument()
    const create = screen.getByRole('button', { name: 'Создать' })
    expect(create).toBeDisabled()

    await user.type(byLabel('Название *'), ' Двор 3 ')
    await user.type(byLabel('GPS Широта'), '41.3')
    await user.click(create)

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(calls[0].body).toEqual({ name: 'Двор 3', description: null, gps_latitude: 41.3, gps_longitude: null, is_active: true })
  })

  it('невалидная широта (> 90) — запроса нет; ошибка API показывается', async () => {
    const user = userEvent.setup()
    const calls = capture('post', 'yards', 409, { detail: 'Такой двор уже есть' })
    const onClose = vi.fn()
    render(<YardFormModal onClose={onClose} />)
    await user.type(byLabel('Название *'), 'Двор')
    await user.type(byLabel('GPS Широта'), '95')
    await user.click(screen.getByRole('button', { name: 'Создать' }))
    expect(calls).toHaveLength(0)

    await user.clear(byLabel('GPS Широта'))
    await user.click(screen.getByRole('button', { name: 'Создать' }))
    expect(await screen.findByText('Такой двор уже есть')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('правка: предзаполнение и PATCH /yards/{id}', async () => {
    const user = userEvent.setup()
    const calls = capture('patch', 'yards/:id', 200, YARDS[0])
    render(<YardFormModal yard={{ ...YARDS[0], description: 'Старый', gps_latitude: 41.1, gps_longitude: 69.9 }} onClose={() => {}} />)
    expect(screen.getByText('Редактировать двор')).toBeInTheDocument()
    expect((byLabel('GPS Долгота') as HTMLInputElement).value).toBe('69.9')
    await user.clear(byLabel('Описание'))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toEqual({ url: '/uk/api/v2/addresses/yards/1', body: { name: 'Двор 1', description: null, gps_latitude: 41.1, gps_longitude: 69.9 } })
  })
})

describe('BuildingFormModal', () => {
  it('создание: двор из пропа, подъезды/этажи не ниже 1, POST /buildings', async () => {
    const user = userEvent.setup()
    const calls = capture('post', 'buildings', 201, BUILDING)
    const onClose = vi.fn()
    render(<BuildingFormModal yardId={2} yards={YARDS} onClose={onClose} />)
    expect(screen.getByText('Новое здание')).toBeInTheDocument()
    expect((byLabel('Двор *') as HTMLSelectElement).value).toBe('2')

    await user.type(byLabel('Адрес *'), ' ул. Новая, 1 ')
    const entrances = byLabel('Подъезды')
    await user.clear(entrances)
    expect(entrances.value).toBe('1') // пустое → минимум 1 (контролируемый input)
    await user.type(entrances, '0') // дописывается к «1» → 10
    await user.selectOptions(byLabel('Двор *'), '1')
    await user.click(screen.getByRole('button', { name: 'Создать' }))

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(calls[0].body).toEqual({ address: 'ул. Новая, 1', yard_id: 1, entrance_count: 10, floor_count: 1, description: null, gps_latitude: null, gps_longitude: null, is_active: true })
  })

  it('правка: предзаполнение из здания и PATCH /buildings/{id}', async () => {
    const user = userEvent.setup()
    const calls = capture('patch', 'buildings/:id', 200, BUILDING)
    render(<BuildingFormModal building={BUILDING} yardId={1} yards={YARDS} onClose={() => {}} />)
    expect(screen.getByText('Редактировать здание')).toBeInTheDocument()
    expect((byLabel('Двор *') as HTMLSelectElement).value).toBe('2')
    expect((byLabel('Этажи') as HTMLInputElement).value).toBe('9')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].url).toBe('/uk/api/v2/addresses/buildings/10')
    expect(calls[0].body).toEqual({ address: 'ул. Тестовая, 5', yard_id: 2, entrance_count: 3, floor_count: 9, description: 'Панель', gps_latitude: 41.3, gps_longitude: 69.2 })
  })
})

describe('AddObjectModal', () => {
  it('шаг выбора типа → двор → назад → здание с первым двором по умолчанию; POST /buildings', async () => {
    const user = userEvent.setup()
    const calls = capture('post', 'buildings', 201, BUILDING)
    const onClose = vi.fn()
    render(<AddObjectModal open onClose={onClose} yards={YARDS} />)
    expect(screen.getByText('Новый объект')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Создать' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Двор/ }))
    expect(screen.getByText('Новый двор')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Выбрать тип/ }))
    await user.click(screen.getByRole('button', { name: /Здание/ }))
    expect(screen.getByText('Новое здание')).toBeInTheDocument()
    expect((byLabel('Двор *') as HTMLSelectElement).value).toBe('1')
    expect(screen.getByRole('button', { name: 'Создать' })).toBeDisabled()

    await user.type(byLabel('Адрес *'), 'ул. Ленина, 3')
    await user.click(screen.getByRole('button', { name: 'Создать' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(calls[0].body).toMatchObject({ address: 'ул. Ленина, 3', yard_id: 1, is_active: true })
  })

  it('preselectedYardId: сразу форма здания без «Выбрать тип»; ошибка API видна', async () => {
    const user = userEvent.setup()
    capture('post', 'buildings', 422, { detail: 'Адрес занят' })
    render(<AddObjectModal open onClose={() => {}} yards={YARDS} preselectedYardId={2} />)
    expect(screen.getByText('Новое здание')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Выбрать тип/ })).not.toBeInTheDocument()
    expect((byLabel('Двор *') as HTMLSelectElement).value).toBe('2')
    await user.type(byLabel('Адрес *'), 'ул. X')
    await user.click(screen.getByRole('button', { name: 'Создать' }))
    expect(await screen.findByText('Адрес занят')).toBeInTheDocument()
  })

  it('двор: POST /yards и закрытие', async () => {
    const user = userEvent.setup()
    const calls = capture('post', 'yards', 201, YARDS[0])
    const onClose = vi.fn()
    render(<AddObjectModal open onClose={onClose} yards={YARDS} />)
    await user.click(screen.getByRole('button', { name: /Двор/ }))
    await user.type(byLabel('Название *'), 'Новый двор')
    await user.click(screen.getByRole('button', { name: 'Создать' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(calls[0].body).toEqual({ name: 'Новый двор', description: null, gps_latitude: null, gps_longitude: null, is_active: true })
  })
})

describe('BulkCreateModal', () => {
  it('диапазоны и списки парсятся с дедупликацией и сортировкой; результат после POST', async () => {
    const user = userEvent.setup()
    const calls = capture('post', 'apartments/bulk', 200, { created: 4, skipped: 1, errors: ['7: занят'] })
    const onClose = vi.fn()
    render(<BulkCreateModal buildingId={10} buildingAddress="ул. Тестовая, 5" onClose={onClose} />)
    expect(screen.getByText('Массовое создание квартир')).toBeInTheDocument()
    expect(screen.getByText('ул. Тестовая, 5')).toBeInTheDocument()
    const create = screen.getByRole('button', { name: 'Создать' })
    expect(create).toBeDisabled()

    await user.type(screen.getByPlaceholderText('Например: 1-50 или 1, 5, 10, 15-20'), '10, 3-5, 3, 12а')
    expect(screen.getByText('Будет создано: 5 квартир')).toBeInTheDocument()
    await user.click(create)

    expect(await screen.findByText('Создано: 4')).toBeInTheDocument()
    expect(screen.getByText('Пропущено (дубли): 1')).toBeInTheDocument()
    expect(screen.getByText('Ошибки: 7: занят')).toBeInTheDocument()
    expect(calls[0].body).toEqual({ building_id: 10, apartment_numbers: ['3', '4', '5', '10', '12а'] })
    await user.click(screen.getByRole('button', { name: 'OK' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('больше 500 номеров — предупреждение и кнопка заблокирована; ошибка API из detail', async () => {
    const user = userEvent.setup()
    capture('post', 'apartments/bulk', 400, { detail: 'Дом не найден' })
    render(<BulkCreateModal buildingId={10} buildingAddress="x" onClose={() => {}} />)
    const input = screen.getByPlaceholderText('Например: 1-50 или 1, 5, 10, 15-20')
    await user.type(input, '1-400, 401-800')
    expect(screen.getByText('Максимум 500 квартир за раз')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Создать' })).toBeDisabled()

    await user.clear(input)
    await user.type(input, '1-3')
    await user.click(screen.getByRole('button', { name: 'Создать' }))
    expect(await screen.findByText('Дом не найден')).toBeInTheDocument()
  })
})
