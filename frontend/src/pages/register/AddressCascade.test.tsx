import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../../test/test-utils'
import { AddressCascade } from './AddressCascade'

// Спека §5.1: двор → дом → квартира крупными кнопками, крошки, «Назад»,
// фильтр квартир по номеру.

function api() {
  return {
    yards: vi.fn().mockResolvedValue([{ id: 1, name: 'Olmazor' }, { id: 2, name: 'Yunusobod' }]),
    buildings: vi.fn().mockResolvedValue([{ id: 5, address: 'Дом 11В' }]),
    apartments: vi.fn().mockResolvedValue([
      { id: 9, apartment_number: '10' },
      { id: 10, apartment_number: '100' },
      { id: 11, apartment_number: '101' },
      { id: 12, apartment_number: '2' },
    ]),
  }
}

describe('AddressCascade', () => {
  it('двор → дом → квартира с крошками и «Назад»', async () => {
    const a = api()
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<AddressCascade ticket="t" api={a} onSelect={onSelect} />)

    await user.click(await screen.findByRole('button', { name: /Olmazor/ }))
    expect(a.buildings).toHaveBeenCalledWith('t', 1)
    expect(await screen.findByRole('button', { name: /Дом 11В/ })).toBeInTheDocument()
    expect(screen.getByText('Olmazor')).toBeInTheDocument() // крошка

    await user.click(screen.getByRole('button', { name: 'Назад' }))
    expect(await screen.findByRole('button', { name: /Yunusobod/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Olmazor/ }))
    await user.click(await screen.findByRole('button', { name: /Дом 11В/ }))
    expect(a.apartments).toHaveBeenCalledWith('t', 5)
    expect(await screen.findByRole('button', { name: '2' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '100' }))
    expect(onSelect).toHaveBeenCalledWith(
      { id: 10, apartment_number: '100' },
      { yard: 'Olmazor', building: 'Дом 11В' },
    )
  })

  it('фильтр по номеру оставляет только совпадения', async () => {
    const a = api()
    const user = userEvent.setup()
    render(<AddressCascade ticket="t" api={a} onSelect={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: /Olmazor/ }))
    await user.click(await screen.findByRole('button', { name: /Дом 11В/ }))
    await screen.findByRole('button', { name: '2' })

    await user.type(screen.getByPlaceholderText('Номер квартиры'), '10')
    expect(screen.queryByRole('button', { name: '2' })).toBeNull()
    expect(screen.getByRole('button', { name: '10' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '100' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '101' })).toBeInTheDocument()
  })

  it('пустой список показывает сообщение', async () => {
    const a = api()
    a.yards.mockResolvedValue([])
    render(<AddressCascade ticket="t" api={a} onSelect={vi.fn()} />)
    expect(await screen.findByText('Ничего не найдено')).toBeInTheDocument()
  })
})
