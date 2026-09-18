import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor, fireEvent, within } from '@testing-library/react'
import { render } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { useAuthStore } from '@/stores/authStore'
import AccessEquipmentPage from './AccessEquipmentPage'

// TEST-068: CRUD-панели «Оборудования» через настоящие хуки + msw. Для каждой
// мутации проверяем метод/URL/тело — форма собирает payload (числа из select,
// JSON из textarea, csv → массив), и именно это ломается молча.

type Captured = { method: string; url: string; body: unknown }

const zone = {
  id: 5, code: 'Z1', name: 'Зона 1', description: null, offline_mode: 'fail_closed',
  parking_type: 'assigned', capacity: null, max_permanent_vehicles_per_apartment: null,
  is_active: true, yard_ids: [1, 2],
}
const sharedZone = {
  id: 6, code: 'Z2', name: 'Общая', description: null, offline_mode: 'fail_closed',
  parking_type: 'shared', capacity: 10, max_permanent_vehicles_per_apartment: 2,
  is_active: true, yard_ids: [],
}
const gate = { id: 1, code: 'G1', zone_id: 5, direction: 'entry', name: 'Главный', is_active: true }
const camera = { id: 21, code: 'CAM1', gate_id: 1, direction: 'entry', name: null, vendor: 'Hik', model: 'DS-2', attributes: { fps: 25 }, is_active: true }
const barrier = { id: 31, code: 'BAR1', gate_id: 1, name: null, relay_type: 'relay', relay_channel: 2, config: null, is_active: true }
const controller = { id: 9, controller_uid: 'ctrl-001', name: 'Контроллер', zone_id: 5, gate_id: 1, offline_mode: 'fail_closed', ip_allowlist: ['10.0.0.1'], pinned_public_key_id: null, status: 'online', is_active: true }
const spot = { id: 3, zone_id: 5, code: 'A-01', status: 'active' }

function list(items: unknown[]) {
  return HttpResponse.json({ items, total: items.length, limit: 50, offset: 0 })
}

function installHandlers(captured: Captured[]) {
  const capture = async ({ request }: { request: Request }) => {
    const url = new URL(request.url)
    const body = request.method === 'POST' || request.method === 'PATCH' ? await request.json().catch(() => null) : null
    captured.push({ method: request.method, url: url.pathname + url.search, body })
  }
  server.use(
    http.get('*/api/v1/access/admin/zones', () => list([zone, sharedZone])),
    http.get('*/api/v1/access/admin/zones/:id/occupancy', ({ params }) =>
      HttpResponse.json({ zone_id: Number(params.id), occupancy: 3, capacity: 10 }),
    ),
    http.get('*/api/v1/access/admin/gates', () => list([gate])),
    http.get('*/api/v1/access/admin/cameras', () => list([camera])),
    http.get('*/api/v1/access/admin/barriers', () => list([barrier])),
    http.get('*/api/v1/access/admin/controllers', () => list([controller])),
    http.get('*/api/v1/access/admin/spots', ({ request }) => {
      const url = new URL(request.url)
      captured.push({ method: 'GET', url: url.pathname + url.search, body: null })
      return list([spot])
    }),
    http.get('*/api/v1/access/admin/spot-assignments', () => list([])),
    http.post('*/api/v1/access/admin/zones', async (info) => { await capture(info); return HttpResponse.json({ ...zone, id: 7 }, { status: 201 }) }),
    http.patch('*/api/v1/access/admin/zones/:id', async (info) => { await capture(info); return HttpResponse.json(zone) }),
    http.post('*/api/v1/access/admin/zones/:id/yards', async (info) => { await capture(info); return HttpResponse.json(zone) }),
    http.post('*/api/v1/access/admin/spots', async (info) => { await capture(info); return HttpResponse.json({ ...spot, id: 8 }, { status: 201 }) }),
    http.patch('*/api/v1/access/admin/spots/:id', async (info) => { await capture(info); return HttpResponse.json(spot) }),
    http.post('*/api/v1/access/admin/gates', async (info) => { await capture(info); return HttpResponse.json({ ...gate, id: 2 }, { status: 201 }) }),
    http.patch('*/api/v1/access/admin/gates/:id', async (info) => { await capture(info); return HttpResponse.json(gate) }),
    http.post('*/api/v1/access/admin/cameras', async (info) => { await capture(info); return HttpResponse.json({ ...camera, id: 22 }, { status: 201 }) }),
    http.patch('*/api/v1/access/admin/cameras/:id', async (info) => { await capture(info); return HttpResponse.json(camera) }),
    http.post('*/api/v1/access/admin/barriers', async (info) => { await capture(info); return HttpResponse.json({ ...barrier, id: 32 }, { status: 201 }) }),
    http.patch('*/api/v1/access/admin/barriers/:id', async (info) => { await capture(info); return HttpResponse.json(barrier) }),
    http.patch('*/api/v1/access/admin/controllers/:id', async (info) => { await capture(info); return HttpResponse.json(controller) }),
    http.post('*/api/v1/access/admin/controllers/:id/rotate-key', async (info) => {
      await capture(info)
      return HttpResponse.json({ ...controller, api_key: 'ROTATED-KEY-ONCE' })
    }),
  )
}

function setRole(role: string) {
  useAuthStore.setState({ user: { id: 1, roles: [role] }, isAuthenticated: true, hydrating: false })
}

function only(captured: Captured[], method: string, urlPart: string) {
  return captured.filter((c) => c.method === method && c.url.includes(urlPart))
}

async function openTab(label: string) {
  await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument())
  fireEvent.click(screen.getByText(label))
}

/** Кнопка строки таблицы по коду строки. */
function rowButton(rowText: string, name: string) {
  const cell = screen.getByText(rowText)
  const row = cell.closest('tr')
  if (!row) throw new Error(`row ${rowText} not found`)
  return within(row).getByRole('button', { name })
}

let captured: Captured[]

beforeEach(() => {
  captured = []
  installHandlers(captured)
})
afterEach(() => useAuthStore.setState({ user: null, isAuthenticated: false }))

describe('AccessEquipmentPage — «Зоны»', () => {
  it('таблица: занятость shared-зоны из occupancy, прочерк для assigned, фазы списком', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByText('Z2')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('3 / 10')).toBeInTheDocument())
    expect(screen.getByText('#1, #2')).toBeInTheDocument()
    // assigned-зона: в колонке занятости прочерк (occupancy не запрашивается).
    const assignedRow = screen.getByText('Z1').closest('tr')!
    expect(within(assignedRow).getAllByText('—').length).toBeGreaterThan(0)
  })

  it('создание: POST /admin/zones с code/name/offline_mode', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Добавить зону' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Добавить зону' }))
    await waitFor(() => expect(screen.getByText('Новая зона')).toBeInTheDocument())

    const addBtn = screen.getByRole('button', { name: 'Добавить' })
    expect(addBtn).toBeDisabled() // код и название обязательны

    fireEvent.change(document.getElementById('zf-code')!, { target: { value: 'Z9' } })
    fireEvent.change(document.getElementById('zf-name')!, { target: { value: 'Новая' } })
    expect(addBtn).toBeEnabled()
    fireEvent.click(addBtn)

    await waitFor(() => expect(only(captured, 'POST', '/admin/zones').length).toBe(1))
    expect(only(captured, 'POST', '/admin/zones')[0].body).toMatchObject({ code: 'Z9', name: 'Новая', offline_mode: 'fail_closed' })
    await waitFor(() => expect(screen.queryByText('Новая зона')).not.toBeInTheDocument())
  })

  it('редактирование: PATCH /admin/zones/5, привязка/отвязка фазы → POST /yards', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByText('Z1')).toBeInTheDocument())
    fireEvent.click(rowButton('Z1', 'Редактировать'))
    await waitFor(() => expect(screen.getByText('Редактирование зоны')).toBeInTheDocument())

    // Фазы редактируемой зоны показаны, отвязка шлёт remove.
    fireEvent.click(screen.getByRole('button', { name: 'Отвязать фазу #2' }))
    await waitFor(() => expect(only(captured, 'POST', '/admin/zones/5/yards').length).toBe(1))
    expect(only(captured, 'POST', '/admin/zones/5/yards')[0].body).toEqual({ remove: [2] })

    // Привязка новой фазы шлёт add.
    fireEvent.change(screen.getByPlaceholderText('ID фазы'), { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: 'Привязать' }))
    await waitFor(() => expect(only(captured, 'POST', '/admin/zones/5/yards').length).toBe(2))
    expect(only(captured, 'POST', '/admin/zones/5/yards')[1].body).toEqual({ add: [7] })

    // Сохранение формы — PATCH с новым названием.
    fireEvent.change(document.getElementById('zf-name')!, { target: { value: 'Переименована' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/zones/5').length).toBe(1))
    expect(only(captured, 'PATCH', '/admin/zones/5')[0].body).toMatchObject({ code: 'Z1', name: 'Переименована', is_active: true })
  })

  it('деактивация: подтверждение → PATCH is_active=false', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByText('Z1')).toBeInTheDocument())
    fireEvent.click(rowButton('Z1', 'Деактивировать'))
    await waitFor(() => expect(screen.getByText('Деактивация')).toBeInTheDocument())
    expect(screen.getByText(/Деактивировать «Z1»/)).toBeInTheDocument()

    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Деактивировать' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/zones/5').length).toBe(1))
    expect(only(captured, 'PATCH', '/admin/zones/5')[0].body).toEqual({ code: 'Z1', name: 'Зона 1', offline_mode: 'fail_closed', is_active: false })
    await waitFor(() => expect(screen.queryByText('Деактивация')).not.toBeInTheDocument())
  })

  it('ошибка загрузки зон → текст ошибки вместо таблицы', async () => {
    server.use(http.get('*/api/v1/access/admin/zones', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    setRole('manager')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByText('Ошибка')).toBeInTheDocument())
    expect(screen.queryByText('Z1')).not.toBeInTheDocument()
  })
})

describe('AccessEquipmentPage — «Места»', () => {
  it('фильтр по зоне уходит в GET /admin/spots?zone_id', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await openTab('Места')
    await waitFor(() => expect(screen.getByText('A-01')).toBeInTheDocument())
    // Подпись зоны в строке (тот же текст есть и в <option> фильтра).
    expect(within(screen.getByText('A-01').closest('tr')!).getByText('Z1 — Зона 1')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Зона'), { target: { value: '6' } })
    await waitFor(() => expect(only(captured, 'GET', '/admin/spots?zone_id=6').length).toBe(1))
  })

  it('создание: POST /admin/spots с числовым zone_id и кодом', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await openTab('Места')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Добавить место' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Добавить место' }))
    await waitFor(() => expect(screen.getByText('Новое место')).toBeInTheDocument())

    fireEvent.change(document.getElementById('eq-zone_id')!, { target: { value: '6' } })
    fireEvent.change(document.getElementById('eq-code')!, { target: { value: 'B-07' } })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))

    await waitFor(() => expect(only(captured, 'POST', '/admin/spots').length).toBe(1))
    expect(only(captured, 'POST', '/admin/spots')[0].body).toEqual({ zone_id: 6, code: 'B-07' })
  })

  it('редактирование шлёт только code/status; деактивация → status=inactive', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await openTab('Места')
    await waitFor(() => expect(screen.getByText('A-01')).toBeInTheDocument())

    fireEvent.click(rowButton('A-01', 'Редактировать'))
    await waitFor(() => expect(screen.getByText('Редактирование места')).toBeInTheDocument())
    fireEvent.change(document.getElementById('eq-status')!, { target: { value: 'inactive' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/spots/3').length).toBe(1))
    expect(only(captured, 'PATCH', '/admin/spots/3')[0].body).toEqual({ code: 'A-01', status: 'inactive' })

    fireEvent.click(rowButton('A-01', 'Деактивировать'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Деактивировать' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/spots/3').length).toBe(2))
    expect(only(captured, 'PATCH', '/admin/spots/3')[1].body).toEqual({ status: 'inactive' })
  })
})

describe('AccessEquipmentPage — «Въезды»', () => {
  it('таблица + создание: POST /admin/gates с zone_id числом и направлением', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await openTab('Въезды')
    await waitFor(() => expect(screen.getByText('G1')).toBeInTheDocument())
    expect(screen.getByText('Главный')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Добавить въезд' }))
    await waitFor(() => expect(screen.getByText('Новый въезд')).toBeInTheDocument())
    fireEvent.change(document.getElementById('eq-code')!, { target: { value: 'G2' } })
    fireEvent.change(document.getElementById('eq-direction')!, { target: { value: 'exit' } })
    fireEvent.change(document.getElementById('eq-name')!, { target: { value: 'Задний' } })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))

    await waitFor(() => expect(only(captured, 'POST', '/admin/gates').length).toBe(1))
    expect(only(captured, 'POST', '/admin/gates')[0].body).toEqual({ code: 'G2', zone_id: 5, direction: 'exit', name: 'Задний' })
  })

  it('редактирование снимает «Активен» → PATCH is_active=false; деактивация — тот же PATCH', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await openTab('Въезды')
    await waitFor(() => expect(screen.getByText('G1')).toBeInTheDocument())

    fireEvent.click(rowButton('G1', 'Редактировать'))
    await waitFor(() => expect(screen.getByText('Редактирование въезда')).toBeInTheDocument())
    const active = document.getElementById('eq-is_active') as HTMLInputElement
    expect(active.checked).toBe(true)
    fireEvent.click(active)
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/gates/1').length).toBe(1))
    expect(only(captured, 'PATCH', '/admin/gates/1')[0].body).toMatchObject({ code: 'G1', zone_id: 5, direction: 'entry', is_active: false })

    fireEvent.click(rowButton('G1', 'Деактивировать'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Деактивировать' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/gates/1').length).toBe(2))
    expect(only(captured, 'PATCH', '/admin/gates/1')[1].body).toEqual({ code: 'G1', zone_id: 5, direction: 'entry', is_active: false })
  })
})

describe('AccessEquipmentPage — «Камеры» (system_admin)', () => {
  it('таблица показывает вендор+модель; создание с JSON-атрибутами → объект в теле', async () => {
    setRole('system_admin')
    render(<AccessEquipmentPage />)
    await openTab('Камеры')
    await waitFor(() => expect(screen.getByText('CAM1')).toBeInTheDocument())
    expect(screen.getByText('Hik DS-2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Добавить камеру' }))
    await waitFor(() => expect(screen.getByText('Новая камера')).toBeInTheDocument())
    fireEvent.change(document.getElementById('eq-code')!, { target: { value: 'CAM2' } })
    fireEvent.change(document.getElementById('eq-attributes')!, { target: { value: '{ not json' } })
    expect(screen.getByText('Невалидный JSON')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Добавить' })).toBeDisabled()

    fireEvent.change(document.getElementById('eq-attributes')!, { target: { value: '{"fps": 30}' } })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))
    await waitFor(() => expect(only(captured, 'POST', '/admin/cameras').length).toBe(1))
    expect(only(captured, 'POST', '/admin/cameras')[0].body).toEqual({ code: 'CAM2', gate_id: 1, direction: 'entry', attributes: { fps: 30 } })
  })

  it('редактирование → PATCH /admin/cameras/21; деактивация → is_active=false', async () => {
    setRole('system_admin')
    render(<AccessEquipmentPage />)
    await openTab('Камеры')
    await waitFor(() => expect(screen.getByText('CAM1')).toBeInTheDocument())

    fireEvent.click(rowButton('CAM1', 'Редактировать'))
    await waitFor(() => expect(screen.getByText('Редактирование камеры')).toBeInTheDocument())
    fireEvent.change(document.getElementById('eq-vendor')!, { target: { value: 'Dahua' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/cameras/21').length).toBe(1))
    expect(only(captured, 'PATCH', '/admin/cameras/21')[0].body).toMatchObject({ code: 'CAM1', vendor: 'Dahua', attributes: { fps: 25 }, is_active: true })

    fireEvent.click(rowButton('CAM1', 'Деактивировать'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Деактивировать' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/cameras/21').length).toBe(2))
    expect(only(captured, 'PATCH', '/admin/cameras/21')[1].body).toEqual({ code: 'CAM1', gate_id: 1, direction: 'entry', is_active: false })
  })
})

describe('AccessEquipmentPage — «Шлагбаумы» (system_admin)', () => {
  it('таблица показывает реле с каналом; создание → POST с relay_channel числом', async () => {
    setRole('system_admin')
    render(<AccessEquipmentPage />)
    await openTab('Шлагбаумы')
    await waitFor(() => expect(screen.getByText('BAR1')).toBeInTheDocument())
    expect(screen.getByText('relay #2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Добавить шлагбаум' }))
    await waitFor(() => expect(screen.getByText('Новый шлагбаум')).toBeInTheDocument())
    fireEvent.change(document.getElementById('eq-code')!, { target: { value: 'BAR2' } })
    fireEvent.change(document.getElementById('eq-relay_channel')!, { target: { value: '4' } })
    fireEvent.change(document.getElementById('eq-config')!, { target: { value: '{"pulse_ms": 500}' } })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))
    await waitFor(() => expect(only(captured, 'POST', '/admin/barriers').length).toBe(1))
    expect(only(captured, 'POST', '/admin/barriers')[0].body).toEqual({ code: 'BAR2', gate_id: 1, relay_channel: 4, config: { pulse_ms: 500 } })
  })

  it('деактивация → PATCH /admin/barriers/31 is_active=false', async () => {
    setRole('system_admin')
    render(<AccessEquipmentPage />)
    await openTab('Шлагбаумы')
    await waitFor(() => expect(screen.getByText('BAR1')).toBeInTheDocument())
    fireEvent.click(rowButton('BAR1', 'Деактивировать'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Деактивировать' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/barriers/31').length).toBe(1))
    expect(only(captured, 'PATCH', '/admin/barriers/31')[0].body).toEqual({ code: 'BAR1', gate_id: 1, is_active: false })
  })
})

describe('AccessEquipmentPage — «Контроллеры»: редактирование, ротация, деактивация', () => {
  it('редактирование: csv-allowlist → массив в PATCH', async () => {
    setRole('system_admin')
    render(<AccessEquipmentPage />)
    await openTab('Контроллеры')
    await waitFor(() => expect(screen.getByText('ctrl-001')).toBeInTheDocument())
    expect(screen.getByText('10.0.0.1')).toBeInTheDocument()

    fireEvent.click(rowButton('ctrl-001', 'Редактировать'))
    await waitFor(() => expect(screen.getByText('Редактирование контроллера')).toBeInTheDocument())
    fireEvent.change(document.getElementById('eq-ip_allowlist')!, { target: { value: '10.0.0.1, 10.0.0.2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/controllers/9').length).toBe(1))
    expect(only(captured, 'PATCH', '/admin/controllers/9')[0].body).toMatchObject({
      controller_uid: 'ctrl-001', zone_id: 5, gate_id: 1, ip_allowlist: ['10.0.0.1', '10.0.0.2'], is_active: true,
    })
  })

  it('ротация ключа: подтверждение → POST rotate-key → ключ показан один раз', async () => {
    setRole('system_admin')
    render(<AccessEquipmentPage />)
    await openTab('Контроллеры')
    await waitFor(() => expect(screen.getByText('ctrl-001')).toBeInTheDocument())

    fireEvent.click(rowButton('ctrl-001', 'Ротировать ключ'))
    await waitFor(() => expect(screen.getByText('Ротация ключа')).toBeInTheDocument())
    expect(screen.getByText(/новый API-ключ для контроллера «ctrl-001»/)).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ротировать ключ' }))

    await waitFor(() => expect(only(captured, 'POST', '/admin/controllers/9/rotate-key').length).toBe(1))
    await waitFor(() => expect(screen.getByText('ROTATED-KEY-ONCE')).toBeInTheDocument())
    expect(screen.getAllByText('ROTATED-KEY-ONCE')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Готово, я сохранил ключ' }))
    await waitFor(() => expect(screen.queryByText('ROTATED-KEY-ONCE')).not.toBeInTheDocument())
  })

  it('деактивация → PATCH /admin/controllers/9 {is_active:false}', async () => {
    setRole('system_admin')
    render(<AccessEquipmentPage />)
    await openTab('Контроллеры')
    await waitFor(() => expect(screen.getByText('ctrl-001')).toBeInTheDocument())
    fireEvent.click(rowButton('ctrl-001', 'Деактивировать'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Деактивировать' }))
    await waitFor(() => expect(only(captured, 'PATCH', '/admin/controllers/9').length).toBe(1))
    expect(only(captured, 'PATCH', '/admin/controllers/9')[0].body).toEqual({ is_active: false })
  })
})
