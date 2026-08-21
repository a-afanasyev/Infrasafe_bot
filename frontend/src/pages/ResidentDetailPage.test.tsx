import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../test/test-utils'
import ResidentDetailPage from './ResidentDetailPage'
import type { ResidentProfile } from '../types/api'

const { detailQuery, renameSpy } = vi.hoisted(() => ({
  detailQuery: {
    data: undefined as ResidentProfile | undefined,
    isLoading: false,
    isError: false,
  },
  renameSpy: vi.fn(),
}))

// vi.mock поднимается наверх файла, поэтому фабрика не имеет права ссылаться
// на переменные модуля — хелпер объявляется прямо внутри неё.
vi.mock('../hooks/useResidents', () => {
  const noop = () => ({ mutate: vi.fn(), isPending: false })
  return {
    useResident: () => detailQuery,
    useRenameResident: () => ({ mutate: renameSpy, isPending: false }),
    useApproveResident: noop,
    useBlockResident: noop,
    useUnblockResident: noop,
    useAttachApartment: noop,
    useApproveBinding: noop,
    useRejectBinding: noop,
    useUpdateBinding: noop,
    useRemoveBinding: noop,
    useRequestDocuments: noop,
    useApproveVerification: noop,
    useRejectVerification: noop,
    useResidentsWebSocket: () => undefined,
  }
})

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return { ...actual, useParams: () => ({ id: '1' }), useNavigate: () => vi.fn() }
})

function makeProfile(over: Partial<ResidentProfile> = {}): ResidentProfile {
  return {
    id: 1,
    telegram_id: 5001,
    username: 'ivanov',
    first_name: 'Иван',
    last_name: 'Иванов',
    phone: '+998901112233',
    status: 'approved',
    verification_status: 'requested',
    verification_notes: null,
    verification_date: null,
    language: 'ru',
    created_at: '2026-07-01T10:00:00Z',
    roles: ['applicant'],
    apartments: [{
      id: 11,
      apartment_id: 700,
      apartment_number: '42',
      building_id: 70,
      building_address: 'ул. Тестовая 1',
      yard_id: 7,
      yard_name: 'Двор-7',
      status: 'approved',
      is_owner: true,
      is_primary: true,
      requested_at: '2026-07-01T10:00:00Z',
      reviewed_at: '2026-07-02T10:00:00Z',
      admin_comment: null,
    }],
    documents: [],
    latest_verification: null,
    ...over,
  }
}

beforeEach(() => {
  renameSpy.mockClear()
  detailQuery.data = makeProfile()
  detailQuery.isLoading = false
  detailQuery.isError = false
})

describe('ResidentDetailPage', () => {
  it('показывает профиль и адрес привязки одной строкой двор·дом·кв', () => {
    render(<ResidentDetailPage />)
    expect(screen.getByText('Иван Иванов')).toBeInTheDocument()
    expect(screen.getByText('Двор-7 · ул. Тестовая 1 · кв. 42')).toBeInTheDocument()
    expect(screen.getByText('Основная')).toBeInTheDocument()
    expect(screen.getByText('Владелец')).toBeInTheDocument()
  })

  it('отклонённая привязка остаётся в карточке как история решений', () => {
    const p = makeProfile()
    detailQuery.data = {
      ...p,
      apartments: [...p.apartments, {
        ...p.apartments[0],
        id: 12,
        apartment_number: '43',
        status: 'rejected',
        is_primary: false,
        is_owner: false,
        admin_comment: 'Не подтверждено документами',
      }],
    }
    render(<ResidentDetailPage />)
    expect(screen.getByText('Отклонена')).toBeInTheDocument()
    expect(screen.getByText('Не подтверждено документами')).toBeInTheDocument()
  })

  it('роль сотрудника показана рядом со статусами — это причина прятать блокировку', () => {
    detailQuery.data = makeProfile({ roles: ['applicant', 'executor'] })
    render(<ResidentDetailPage />)
    expect(screen.getByText('Исполнитель')).toBeInTheDocument()
  })

  it('пустые секции не ломают карточку', () => {
    render(<ResidentDetailPage />)
    expect(screen.getByText(/Документы не загружены/)).toBeInTheDocument()
    expect(screen.getByText(/Записей о верификации нет/)).toBeInTheDocument()
  })

  it('ошибка загрузки показывает «не найден», а не пустой экран', () => {
    detailQuery.isError = true
    detailQuery.data = undefined
    render(<ResidentDetailPage />)
    expect(screen.getByText(/Жители не найдены/)).toBeInTheDocument()
  })
})

describe('ResidentDetailPage — исправление ФИО', () => {
  it('открывает форму, предзаполненную текущим ФИО', async () => {
    const user = userEvent.setup()
    render(<ResidentDetailPage />)
    await user.click(screen.getByRole('button', { name: 'Исправить ФИО' }))
    expect(screen.getByLabelText('ФИО')).toHaveValue('Иван Иванов')
  })

  it('шлёт нормализованное ФИО одной строкой', async () => {
    const user = userEvent.setup()
    render(<ResidentDetailPage />)
    await user.click(screen.getByRole('button', { name: 'Исправить ФИО' }))

    const field = screen.getByLabelText('ФИО')
    await user.clear(field)
    await user.type(field, '  Иванов   Иван Иванович ')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(renameSpy).toHaveBeenCalledTimes(1)
    expect(renameSpy.mock.calls[0][0]).toBe('Иванов Иван Иванович')
  })

  it('не шлёт запрос, если ФИО не изменилось', async () => {
    const user = userEvent.setup()
    render(<ResidentDetailPage />)
    await user.click(screen.getByRole('button', { name: 'Исправить ФИО' }))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    expect(renameSpy).not.toHaveBeenCalled()
  })

  it('житель без имени тоже правится — форма пустая, кнопка живая', async () => {
    detailQuery.data = makeProfile({ first_name: null, last_name: null })
    const user = userEvent.setup()
    render(<ResidentDetailPage />)
    await user.click(screen.getByRole('button', { name: 'Исправить ФИО' }))

    const field = screen.getByLabelText('ФИО')
    expect(field).toHaveValue('')
    await user.type(field, 'Новый Житель')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    expect(renameSpy.mock.calls[0][0]).toBe('Новый Житель')
  })
})
