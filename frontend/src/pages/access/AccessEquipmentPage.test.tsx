import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { render } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { useAuthStore } from '@/stores/authStore'
import AccessEquipmentPage from './AccessEquipmentPage'

// Раздел «Оборудование»: гейтинг табов по роли + показ api_key контроллера РОВНО
// ОДИН РАЗ в модалке (и его отсутствие в таблице).

const zone = { id: 5, code: 'Z1', name: 'Зона 1', description: null, offline_mode: 'fail_closed', max_permanent_vehicles_per_apartment: null, is_active: true, yard_ids: [] }
const gate = { id: 1, code: 'G1', zone_id: 5, direction: 'entry', name: null, is_active: true }
const controller = { id: 9, controller_uid: 'ctrl-001', name: null, zone_id: 5, gate_id: 1, offline_mode: 'fail_closed', ip_allowlist: null, pinned_public_key_id: null, status: 'online', is_active: true }

function installCommonHandlers() {
  server.use(
    http.get('*/api/v1/access/admin/zones', () =>
      HttpResponse.json({ items: [zone], total: 1, limit: 50, offset: 0 }),
    ),
    http.get('*/api/v1/access/admin/gates', () =>
      HttpResponse.json({ items: [gate], total: 1, limit: 50, offset: 0 }),
    ),
    http.get('*/api/v1/access/admin/cameras', () =>
      HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
    ),
    http.get('*/api/v1/access/admin/barriers', () =>
      HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
    ),
    http.get('*/api/v1/access/admin/controllers', () =>
      HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
    ),
    http.get('*/api/v1/access/admin/spots', () =>
      HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
    ),
    http.get('*/api/v1/access/admin/spot-assignments', () =>
      HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
    ),
  )
}

function setRole(role: string) {
  useAuthStore.setState({ user: { id: 1, roles: [role] }, isAuthenticated: true, hydrating: false })
}

describe('AccessEquipmentPage — гейтинг табов по роли', () => {
  beforeEach(installCommonHandlers)
  afterEach(() => useAuthStore.setState({ user: null, isAuthenticated: false }))

  it('manager видит «Зоны» и «Въезды», но НЕ камеры/шлагбаумы/контроллеры', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByText('Зоны')).toBeInTheDocument())
    expect(screen.getByText('Въезды')).toBeInTheDocument()
    expect(screen.queryByText('Камеры')).not.toBeInTheDocument()
    expect(screen.queryByText('Шлагбаумы')).not.toBeInTheDocument()
    expect(screen.queryByText('Контроллеры')).not.toBeInTheDocument()
  })

  it('manager видит парковочные табы «Места» и «Закрепления»', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByText('Зоны')).toBeInTheDocument())
    expect(screen.getByText('Места')).toBeInTheDocument()
    expect(screen.getByText('Закрепления')).toBeInTheDocument()

    // Переход на «Закрепления» показывает кнопку «Закрепить место».
    fireEvent.click(screen.getByText('Закрепления'))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Закрепить место' })).toBeInTheDocument(),
    )
  })

  it('system_admin видит все 5 табов', async () => {
    setRole('system_admin')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByText('Зоны')).toBeInTheDocument())
    expect(screen.getByText('Въезды')).toBeInTheDocument()
    expect(screen.getByText('Камеры')).toBeInTheDocument()
    expect(screen.getByText('Шлагбаумы')).toBeInTheDocument()
    expect(screen.getByText('Контроллеры')).toBeInTheDocument()
  })
})

describe('AccessEquipmentPage — таб «Закрепления»: лимит/занятость/освободить', () => {
  const spot = { id: 3, zone_id: 5, code: 'A-01', status: 'active' }
  const assignment = {
    id: 4,
    spot_id: 3,
    apartment_id: 12,
    ownership_type: 'owned',
    valid_from: null,
    valid_until: null,
    status: 'active',
    enforce_limit: true,
    occupied: 1,
    spots: 2,
    approved_by_user_id: 7,
    approved_at: null,
  }

  beforeEach(() => {
    installCommonHandlers()
    server.use(
      http.get('*/api/v1/access/admin/spots', () =>
        HttpResponse.json({ items: [spot], total: 1, limit: 50, offset: 0 }),
      ),
      http.get('*/api/v1/access/admin/spot-assignments', () =>
        HttpResponse.json({ items: [assignment], total: 1, limit: 50, offset: 0 }),
      ),
    )
  })
  afterEach(() => useAuthStore.setState({ user: null, isAuthenticated: false }))

  async function openAssignmentsTab() {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByText('Закрепления')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Закрепления'))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Закрепить место' })).toBeInTheDocument(),
    )
  }

  it('рендерит занятость «1 из 2»', async () => {
    await openAssignmentsTab()
    expect(await screen.findByText('1 из 2')).toBeInTheDocument()
  })

  it('переключатель лимита зовёт PATCH с enforce_limit=false', async () => {
    let body: unknown = null
    server.use(
      http.patch('*/api/v1/access/admin/spot-assignments/4', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...assignment, enforce_limit: false })
      }),
    )
    await openAssignmentsTab()
    const toggle = await screen.findByRole('switch')
    fireEvent.click(toggle)
    await waitFor(() => expect(body).toMatchObject({ enforce_limit: false }))
  })

  it('«Освободить место» открывает список сессий и закрывает выбранную', async () => {
    let closed: number | null = null
    server.use(
      http.get('*/api/v1/access/admin/presence', () =>
        HttpResponse.json({
          items: [
            { id: 11, vehicle_id: 9, plate_normalized: '01A001AA', apartment_id: 12, zone_id: 5, entered_at: '2026-06-28T10:00:00Z' },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
      http.post('*/api/v1/access/presence/11/close', () => {
        closed = 11
        return HttpResponse.json({ session_id: 11, status: 'closed', closed_by_user_id: 7, replayed: false })
      }),
    )
    await openAssignmentsTab()
    fireEvent.click(await screen.findByRole('button', { name: 'Освободить место' }))
    // В диалоге появилась сессия с номером авто.
    expect(await screen.findByText('01A001AA')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Освободить' }))
    await waitFor(() => expect(closed).toBe(11))
  })
})

describe('AccessEquipmentPage — api_key контроллера', () => {
  beforeEach(installCommonHandlers)
  afterEach(() => useAuthStore.setState({ user: null, isAuthenticated: false }))

  it('создание контроллера показывает api_key один раз в модалке (и нет в таблице)', async () => {
    server.use(
      http.post('*/api/v1/access/admin/controllers', () =>
        HttpResponse.json(
          { id: 9, controller_uid: 'ctrl-001', name: null, zone_id: 5, gate_id: null, offline_mode: 'fail_closed', ip_allowlist: null, pinned_public_key_id: null, status: 'online', is_active: true, api_key: 'SECRET-PLAINTEXT-KEY' },
          { status: 201 },
        ),
      ),
    )
    setRole('system_admin')
    render(<AccessEquipmentPage />)

    await waitFor(() => expect(screen.getByText('Контроллеры')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Контроллеры'))

    // Открываем форму создания.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Добавить контроллер' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Добавить контроллер' }))

    // Заполняем обязательный UID и сохраняем.
    fireEvent.change(screen.getByLabelText('UID контроллера'), { target: { value: 'ctrl-001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))

    // Ключ показан ровно один раз в модалке + предупреждение.
    await waitFor(() => expect(screen.getByText('SECRET-PLAINTEXT-KEY')).toBeInTheDocument())
    expect(screen.getByText(/показывается один раз/)).toBeInTheDocument()
    // Ключ присутствует только в модалке (одно вхождение), не в таблице.
    expect(screen.getAllByText('SECRET-PLAINTEXT-KEY')).toHaveLength(1)

    // Закрываем модалку — ключ исчезает (повторно не показывается).
    fireEvent.click(screen.getByRole('button', { name: 'Готово, я сохранил ключ' }))
    await waitFor(() => expect(screen.queryByText('SECRET-PLAINTEXT-KEY')).not.toBeInTheDocument())
  })
})

describe('AccessEquipmentPage — тест точки въезда (диагностика)', () => {
  beforeEach(() => {
    server.use(
      http.get('*/api/v1/access/admin/zones', () =>
        HttpResponse.json({ items: [zone], total: 1, limit: 50, offset: 0 }),
      ),
      http.get('*/api/v1/access/admin/gates', () =>
        HttpResponse.json({ items: [gate], total: 1, limit: 50, offset: 0 }),
      ),
      http.get('*/api/v1/access/admin/cameras', () =>
        HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
      ),
      http.get('*/api/v1/access/admin/barriers', () =>
        HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
      ),
      http.get('*/api/v1/access/admin/controllers', () =>
        HttpResponse.json({ items: [controller], total: 1, limit: 50, offset: 0 }),
      ),
    )
  })
  afterEach(() => useAuthStore.setState({ user: null, isAuthenticated: false }))

  it('«Тест» открывает диалог, запуск зовёт верный эндпоинт с телом, рендерит решение', async () => {
    let capturedUrl = ''
    let capturedBody: unknown = null
    server.use(
      http.post('*/api/v1/access/admin/controllers/:id/test-event', async ({ request, params }) => {
        capturedUrl = String(params.id)
        capturedBody = await request.json()
        return HttpResponse.json({
          decision: 'allow',
          status: 'allowed',
          reason: 'permanent_vehicle_allowed',
          decision_id: 77,
          event_id: 'evt-diag-1',
          zone_id: 5,
          gate_id: 1,
          barrier_id: 3,
          command: { command_id: 'cmd-1', barrier_id: 3 },
        })
      }),
    )
    setRole('system_admin')
    render(<AccessEquipmentPage />)

    await waitFor(() => expect(screen.getByText('Контроллеры')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Контроллеры'))

    // Строковое действие «Тест» открывает диалог.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Тест' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Тест' }))

    await waitFor(() => expect(screen.getByText('Тест точки въезда')).toBeInTheDocument())

    // Запускаем тест с дефолтным номером DIAG0001.
    fireEvent.click(screen.getByRole('button', { name: 'Запустить' }))

    // Результат: бейдж решения + ID события из ответа.
    await waitFor(() => expect(screen.getByText('evt-diag-1')).toBeInTheDocument())
    expect(screen.getByText('Разрешён')).toBeInTheDocument()
    expect(screen.getByText(/cmd-1/)).toBeInTheDocument()

    // Эндпоинт и тело запроса корректны.
    expect(capturedUrl).toBe('9')
    expect(capturedBody).toMatchObject({ plate_number: 'DIAG0001', direction: 'entry', confidence: 0.99 })
  })

  it('действие «Тест» скрыто для не-system_admin (manager не видит таб контроллеров)', async () => {
    setRole('manager')
    render(<AccessEquipmentPage />)
    await waitFor(() => expect(screen.getByText('Зоны')).toBeInTheDocument())
    expect(screen.queryByText('Контроллеры')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Тест' })).not.toBeInTheDocument()
  })
})
