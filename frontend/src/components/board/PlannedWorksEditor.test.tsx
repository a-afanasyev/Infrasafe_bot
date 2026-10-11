import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, within } from '../../test/test-utils'
import type { PlannedWorkCfg } from '../../types/boardConfig'
import PlannedWorksEditor, { MAX_PLANNED_WORKS } from './PlannedWorksEditor'

const EMPTY = { ru: '', uz: '' }

function work(id: string): PlannedWorkCfg {
  return { id, date: '2026-10-15', time_from: '10:00', time_to: '12:00', title: { ru: id, uz: '' }, place: EMPTY, text: EMPTY }
}

describe('PlannedWorksEditor', () => {
  it('добавляет работу на сегодня с пустыми полями', () => {
    const onChange = vi.fn()
    render(<PlannedWorksEditor works={[]} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /Добавить работу/ }))
    const [next] = onChange.mock.calls[0]
    expect(next).toHaveLength(1)
    expect(next[0].date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(next[0].title).toEqual(EMPTY)
  })

  it('правка поля отдаёт новый список, исходный не мутирует', () => {
    const works = [work('a'), work('b')]
    const onChange = vi.fn()
    render(<PlannedWorksEditor works={works} onChange={onChange} />)
    const second = screen.getAllByTestId('planned-work')[1]
    const title = within(within(second).getByText('Что делаем').parentElement as HTMLElement).getByPlaceholderText('RU')
    fireEvent.change(title, { target: { value: 'Покраска' } })
    const [next] = onChange.mock.calls[0]
    expect(next[1].title.ru).toBe('Покраска')
    expect(works[1].title.ru).toBe('b')
  })

  it('пустую дату не принимает (бэкенд требует YYYY-MM-DD)', () => {
    const onChange = vi.fn()
    render(<PlannedWorksEditor works={[work('a')]} onChange={onChange} />)
    fireEvent.change(screen.getByDisplayValue('2026-10-15'), { target: { value: '' } })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('удаляет работу', () => {
    const onChange = vi.fn()
    render(<PlannedWorksEditor works={[work('a'), work('b')]} onChange={onChange} />)
    fireEvent.click(within(screen.getAllByTestId('planned-work')[0]).getByRole('button', { name: 'remove' }))
    expect(onChange.mock.calls[0][0].map((w: PlannedWorkCfg) => w.id)).toEqual(['b'])
  })

  it('на потолке кнопка добавления выключена', () => {
    const works = Array.from({ length: MAX_PLANNED_WORKS }, (_, i) => work(`w${i}`))
    render(<PlannedWorksEditor works={works} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Добавить работу/ })).toBeDisabled()
  })
})
