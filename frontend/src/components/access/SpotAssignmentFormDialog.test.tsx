import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { render } from '@/test/test-utils'
import SpotAssignmentFormDialog from './SpotAssignmentFormDialog'
import type { SpotRow } from '../../types/access'

const spots: SpotRow[] = [
  { id: 1, zone_id: 5, code: 'A-01', status: 'active' },
  { id: 2, zone_id: 5, code: 'A-02', status: 'active' },
]
const spotLabel = (s: SpotRow) => `Z5 · ${s.code}`

describe('SpotAssignmentFormDialog — валидация аренды', () => {
  it('rented без срока «до» → submit заблокирован, показана подсказка', async () => {
    const onSubmit = vi.fn()
    render(
      <SpotAssignmentFormDialog open spots={spots} spotLabel={spotLabel} onSubmit={onSubmit} onClose={() => {}} />,
    )

    fireEvent.change(screen.getByLabelText('Место'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('ID квартиры'), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText('Тип владения'), { target: { value: 'rented' } })

    // Срок «до» не задан → кнопка «Закрепить» disabled + подсказка.
    const submit = screen.getByRole('button', { name: 'Закрепить' })
    expect(submit).toBeDisabled()
    await waitFor(() =>
      expect(screen.getByText('Для аренды укажите срок действия «до».')).toBeInTheDocument(),
    )
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('rented со сроком «до» → submit вызывает onSubmit с valid_until', () => {
    const onSubmit = vi.fn()
    render(
      <SpotAssignmentFormDialog open spots={spots} spotLabel={spotLabel} onSubmit={onSubmit} onClose={() => {}} />,
    )

    fireEvent.change(screen.getByLabelText('Место'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('ID квартиры'), { target: { value: '45' } })
    fireEvent.change(screen.getByLabelText('Тип владения'), { target: { value: 'rented' } })
    fireEvent.change(screen.getByLabelText(/Действует до/), { target: { value: '2026-12-31T10:00' } })

    fireEvent.click(screen.getByRole('button', { name: 'Закрепить' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    const payload = onSubmit.mock.calls[0][0]
    expect(payload).toMatchObject({ spot_id: 2, apartment_id: 45, ownership_type: 'rented' })
    expect(payload.valid_until).toBeTruthy()
  })

  it('owned без срока «до» → submit активен', () => {
    const onSubmit = vi.fn()
    render(
      <SpotAssignmentFormDialog open spots={spots} spotLabel={spotLabel} onSubmit={onSubmit} onClose={() => {}} />,
    )
    fireEvent.change(screen.getByLabelText('Место'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('ID квартиры'), { target: { value: '12' } })
    // ownership остаётся owned
    expect(screen.getByRole('button', { name: 'Закрепить' })).not.toBeDisabled()
  })
})
