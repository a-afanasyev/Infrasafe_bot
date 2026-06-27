import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { render } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { useAuthStore } from '@/stores/authStore'
import AccessEquipmentPage from './AccessEquipmentPage'

// Раздел «Оборудование»: гейтинг табов по роли + показ api_key контроллера РОВНО
// ОДИН РАЗ в модалке (и его отсутствие в таблице).

const zone = { id: 5, code: 'Z1', name: 'Зона 1', description: null, offline_mode: 'fail_closed', max_permanent_per_apartment: null, is_active: true, yard_ids: [] }
const gate = { id: 1, code: 'G1', zone_id: 5, direction: 'entry', name: null, is_active: true }

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
