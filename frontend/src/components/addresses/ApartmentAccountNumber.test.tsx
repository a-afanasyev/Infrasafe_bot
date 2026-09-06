import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '../../test/test-utils'
import type { ApartmentBrief, ApartmentDetail } from '../../types/api'
import ApartmentFormModal from './ApartmentFormModal'
import ApartmentProfileModal from './ApartmentProfileModal'

// Лицевой счёт «Mening uyim» — единственный ключ связи квартиры с сервисом
// контроля платежей. Менеджер вводит его в форме квартиры и видит в профиле,
// поэтому подпись поля обязана называть сервис, а не просто «лицевой счёт».

const createMutate = vi.fn()
const updateMutate = vi.fn()
const apartmentDetail = vi.fn()

vi.mock('../../hooks/useAddresses', () => ({
  useCreateApartment: () => ({ mutate: createMutate, isPending: false, error: null }),
  useUpdateApartment: () => ({ mutate: updateMutate, isPending: false, error: null }),
  useApartmentDetail: (id: number | null) => apartmentDetail(id),
}))

vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(() => Promise.reject(new Error('offline'))) },
}))

const detail = (over: Partial<ApartmentDetail> = {}): ApartmentDetail => ({
  id: 100,
  building_id: 10,
  apartment_number: '12',
  account_number: '770123456',
  building_address: 'ул. Ленина 1',
  yard_name: 'Двор А',
  entrance: null,
  floor: null,
  rooms_count: null,
  area: null,
  description: null,
  is_active: true,
  created_at: null,
  residents: [],
  ...over,
})

beforeEach(() => {
  createMutate.mockReset()
  updateMutate.mockReset()
  apartmentDetail.mockReset()
})

describe('ApartmentFormModal — лицевой счёт Mening uyim', () => {
  it('отправляет введённый лицевой счёт без пробелов', () => {
    render(<ApartmentFormModal buildingId={10} onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText(/Номер квартиры/), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText(/Mening uyim/), { target: { value: ' 770123456 ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать' }))

    expect(createMutate).toHaveBeenCalledTimes(1)
    expect(createMutate.mock.calls[0][0]).toMatchObject({
      apartment_number: '12',
      account_number: '770123456',
    })
  })

  it('очищенное поле отправляет null, а не пустую строку', () => {
    const apartment = { id: 100, apartment_number: '12', account_number: '770123456' } as ApartmentBrief
    render(<ApartmentFormModal apartment={apartment} buildingId={10} onClose={vi.fn()} />)

    const input = screen.getByLabelText(/Mening uyim/)
    expect(input).toHaveValue('770123456')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(updateMutate.mock.calls[0][0]).toMatchObject({ id: 100, account_number: null })
  })
})

describe('ApartmentProfileModal — лицевой счёт Mening uyim', () => {
  it('показывает счёт в карточке квартиры с подписью сервиса', () => {
    apartmentDetail.mockReturnValue({ data: detail(), isLoading: false, isError: false })
    render(<ApartmentProfileModal apartmentId={100} onClose={vi.fn()} onEdit={vi.fn()} />)

    expect(screen.getAllByText(/Mening uyim/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('770123456').length).toBeGreaterThan(0)
  })

  it('без счёта показывает прочерк, а не пустоту', () => {
    apartmentDetail.mockReturnValue({ data: detail({ account_number: null }), isLoading: false, isError: false })
    render(<ApartmentProfileModal apartmentId={100} onClose={vi.fn()} onEdit={vi.fn()} />)

    expect(screen.getAllByText(/Mening uyim/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Укажите лицевой счёт/)).toBeInTheDocument()
  })
})
