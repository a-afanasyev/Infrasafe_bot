import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { render } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import { useAuthStore } from '@/stores/authStore'
import AccessDatabasePage from './AccessDatabasePage'

// Гейтинг действий менеджера на «Базе доступа»: кнопки создания/блокировки/
// рассмотрения рендерятся ТОЛЬКО для manager/system_admin (ACCESS_MANAGER_ROLES),
// и скрыты для security_operator.

const activeVehicle = {
  id: 10,
  plate_number_original: '01A123BC',
  plate_number_normalized: '01A123BC',
  plate_country: null,
  plate_type: null,
  brand: 'Chevrolet',
  model: 'Cobalt',
  color: null,
  vehicle_class: null,
  status: 'active',
  blocked_reason: null,
  blocked_by_user_id: null,
  blocked_at: null,
  apartments: [],
}

const pendingRequest = {
  id: 42,
  apartment_id: 5,
  created_by_user_id: 1,
  vehicle_id: null,
  plate_number_original: '01A123BC',
  plate_number_normalized: '01A123BC',
  relation_type: 'owner',
  status: 'pending',
  reviewed_by_user_id: null,
  reviewed_at: null,
  review_comment: null,
  created_at: '2026-06-27T10:00:00Z',
}

function installHandlers() {
  server.use(
    http.get('*/api/v1/access/vehicles', () =>
      HttpResponse.json({ items: [activeVehicle], total: 1, limit: 50, offset: 0 }),
    ),
    http.get('*/api/v1/access/passes', () =>
      HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
    ),
    http.get('*/api/v1/access/requests', () =>
      HttpResponse.json({ items: [pendingRequest], total: 1, limit: 50, offset: 0 }),
    ),
  )
}

function setRole(role: string) {
  useAuthStore.setState({
    user: { id: 1, roles: [role] },
    isAuthenticated: true,
    hydrating: false,
  })
}

describe('AccessDatabasePage — гейтинг действий по роли', () => {
  beforeEach(installHandlers)
  afterEach(() => useAuthStore.setState({ user: null, isAuthenticated: false }))

  it('manager видит «Добавить авто» и действия в строке авто', async () => {
    setRole('manager')
    render(<AccessDatabasePage />)
    await waitFor(() => expect(screen.getByText('01A123BC')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Добавить авто' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Заблокировать' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'В архив' })).toBeInTheDocument()
  })

  it('security_operator НЕ видит действий менеджера', async () => {
    setRole('security_operator')
    render(<AccessDatabasePage />)
    await waitFor(() => expect(screen.getByText('01A123BC')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Добавить авто' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Заблокировать' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'В архив' })).not.toBeInTheDocument()
  })

  it('manager: на вкладке «Заявки» видны «Подтвердить»/«Отклонить» для pending', async () => {
    setRole('manager')
    render(<AccessDatabasePage />)
    await waitFor(() => expect(screen.getByText('01A123BC')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Заявки'))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Отклонить' })).toBeInTheDocument()
  })

  it('manager: «Создать taxi-пропуск» на вкладке «Пропуска»', async () => {
    setRole('manager')
    render(<AccessDatabasePage />)
    fireEvent.click(screen.getByText('Пропуска'))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Создать taxi-пропуск' })).toBeInTheDocument(),
    )
  })
})
