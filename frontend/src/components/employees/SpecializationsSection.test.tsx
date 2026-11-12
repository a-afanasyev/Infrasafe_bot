import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '../../test/test-utils'
import SpecializationsSection from './SpecializationsSection'
import DeletedEmployeesList from './DeletedEmployeesList'

const { mockPut, mockGet } = vi.hoisted(() => ({ mockPut: vi.fn(), mockGet: vi.fn() }))
vi.mock('../../api/client', () => ({ apiClient: { put: mockPut, get: mockGet } }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

beforeEach(() => {
  mockPut.mockReset().mockResolvedValue({ data: { id: 7, specialization: ['plumber'] } })
  mockGet.mockReset()
})

describe('SpecializationsSection', () => {
  it('исполнитель без специализаций: предупреждение, выбор и сохранение', async () => {
    const user = userEvent.setup()
    render(<SpecializationsSection employeeId={7} current={[]} />)

    expect(screen.getByText(/исполнитель не получает заявки/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Сантехника/ }))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith('/api/v2/shifts/employees/7/specializations', { specializations: ['plumber'] }),
    )
  })

  it('«Отмена» возвращает сохранённый набор', async () => {
    const user = userEvent.setup()
    render(<SpecializationsSection employeeId={7} current={['plumber']} />)
    const plumber = screen.getByRole('button', { name: /Сантехника/ })
    expect(plumber).toHaveAttribute('aria-pressed', 'true')

    await user.click(plumber)
    expect(plumber).toHaveAttribute('aria-pressed', 'false')
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(plumber).toHaveAttribute('aria-pressed', 'true')
    expect(mockPut).not.toHaveBeenCalled()
  })
})

describe('DeletedEmployeesList', () => {
  it('показывает, кто, когда и почему удалил', async () => {
    mockGet.mockResolvedValue({
      data: [{
        id: 5, full_name: 'Иван Петров', roles: ['executor'], deleted_at: '2026-11-02T10:00:00Z',
        deletion_reason: 'уволен', deleted_by_name: 'Анна Менеджер',
      }],
    })
    render(<DeletedEmployeesList />)

    expect(await screen.findByText('Иван Петров')).toBeInTheDocument()
    expect(screen.getByText('Исполнитель')).toBeInTheDocument()
    expect(screen.getByText('уволен')).toBeInTheDocument()
    expect(screen.getByText('Анна Менеджер')).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith('/api/v2/shifts/employees/deleted')
  })

  it('пустой список — понятный текст', async () => {
    mockGet.mockResolvedValue({ data: [] })
    render(<DeletedEmployeesList />)
    expect(await screen.findByText('Удалённых сотрудников нет')).toBeInTheDocument()
  })
})
