import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '@/test/test-utils'
import ZoneCheckboxes from './ZoneCheckboxes'
import type { ZoneRef } from '../../types/access'

/**
 * Чекбокс-список зон: multi (накопление/снятие) и single (выбор одной снимает
 * прочие), пустой набор → подсказка.
 */
const ZONES: ZoneRef[] = [
  { id: 1, code: 'A', name: 'Паркинг А' },
  { id: 2, code: 'B', name: 'Паркинг Б' },
]

describe('ZoneCheckboxes', () => {
  it('multi: добавляет и снимает зоны', async () => {
    const onChange = vi.fn()
    render(<ZoneCheckboxes zones={ZONES} selected={[1]} onChange={onChange} />)
    // Отметить вторую → к выбранным добавляется 2.
    await userEvent.click(screen.getByRole('checkbox', { name: /Паркинг Б/ }))
    expect(onChange).toHaveBeenLastCalledWith([1, 2])
    // Снять первую → остаётся пусто.
    await userEvent.click(screen.getByRole('checkbox', { name: /Паркинг А/ }))
    expect(onChange).toHaveBeenLastCalledWith([])
  })

  it('single: выбор одной зоны заменяет прочие', async () => {
    const onChange = vi.fn()
    render(
      <ZoneCheckboxes zones={ZONES} selected={[1]} onChange={onChange} mode="single" />,
    )
    await userEvent.click(screen.getByRole('checkbox', { name: /Паркинг Б/ }))
    expect(onChange).toHaveBeenLastCalledWith([2])
  })

  it('пустой набор кандидатов → подсказка', () => {
    render(
      <ZoneCheckboxes
        zones={[]}
        selected={[]}
        onChange={vi.fn()}
        emptyText="Нет зон"
      />,
    )
    expect(screen.getByText('Нет зон')).toBeInTheDocument()
  })
})
