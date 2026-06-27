import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { render } from '@/test/test-utils'
import ZoneFormDialog from './ZoneFormDialog'

// Форма зоны должна отправлять parking_type всегда, а capacity — только для shared.

describe('ZoneFormDialog — парковочные поля', () => {
  it('создание shared-зоны шлёт parking_type=shared + capacity', async () => {
    const onSubmit = vi.fn()
    render(<ZoneFormDialog open zone={null} onSubmit={onSubmit} onClose={() => {}} />)

    fireEvent.change(screen.getByLabelText('Код'), { target: { value: 'Z-PARK' } })
    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Паркинг' } })

    // По умолчанию assigned → поля «Ёмкость» нет.
    expect(screen.queryByLabelText('Ёмкость')).not.toBeInTheDocument()

    // Переключаем на «Общая» → появляется «Ёмкость».
    fireEvent.change(screen.getByLabelText('Тип парковки'), { target: { value: 'shared' } })
    await waitFor(() => expect(screen.getByLabelText('Ёмкость')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Ёмкость'), { target: { value: '80' } })

    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      code: 'Z-PARK',
      name: 'Паркинг',
      parking_type: 'shared',
      capacity: 80,
    })
  })

  it('assigned-зона шлёт parking_type=assigned без capacity', () => {
    const onSubmit = vi.fn()
    render(<ZoneFormDialog open zone={null} onSubmit={onSubmit} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('Код'), { target: { value: 'Z-MAIN' } })
    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Двор' } })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    const payload = onSubmit.mock.calls[0][0]
    expect(payload.parking_type).toBe('assigned')
    expect(payload.capacity).toBeUndefined()
  })
})
