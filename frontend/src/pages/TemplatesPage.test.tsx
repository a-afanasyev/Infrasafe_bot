import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '../test/test-utils'
import { server } from '../test/msw/server'
import type { TemplateBrief } from '../types/api'
import TemplatesPage from './TemplatesPage'

// TEST-068 (порция pages): шаблоны смен — сводка, строки (время с переносом
// через полночь, цикл vs дни недели, спец-ции, авто-тумблер), действия
// (создать смену, редактировать, удалить через подтверждение), пусто/ошибка.

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

function tpl(overrides: Partial<TemplateBrief> & { id: number; name: string }): TemplateBrief {
  return {
    description: null, start_hour: 8, start_minute: 0, duration_hours: 9, default_shift_type: 'regular',
    days_of_week: [0, 1, 2, 3, 4], is_active: true, min_executors: 1, max_executors: 4, auto_create: false,
    required_specializations: null, ...overrides,
  } as TemplateBrief
}

const TEMPLATES: TemplateBrief[] = [
  tpl({ id: 1, name: 'Дневная', description: 'Будни', auto_create: true, required_specializations: ['electrician'] }),
  tpl({ id: 2, name: 'Ночная', start_hour: 22, start_minute: 30, duration_hours: 8, default_shift_type: 'emergency', is_active: false,
        recurrence_mode: 'cycle', cycle_days_on: 2, cycle_days_off: 2, cycle_anchor_date: '2026-09-01', min_executors: 2, max_executors: 2 }),
]

let patches: { id: string; body: unknown }[]
let deletes: string[]
beforeEach(() => {
  patches = []; deletes = []
  server.use(
    http.get('*/api/v2/shifts/templates', () => HttpResponse.json(TEMPLATES)),
    http.get('*/api/v2/shifts/employees', () => HttpResponse.json([], { headers: { 'X-Total-Count': '0' } })),
    http.patch('*/api/v2/shifts/templates/:id', async ({ params, request }) => { patches.push({ id: String(params.id), body: await request.json() }); return HttpResponse.json({}) }),
    http.delete('*/api/v2/shifts/templates/:id', ({ params }) => { deletes.push(String(params.id)); return HttpResponse.json({}) }),
  )
})

describe('TemplatesPage', () => {
  it('сводка и строки: время/перенос через полночь, тип, цикл или дни недели, спец-ции, исполнители', async () => {
    render(<TemplatesPage />)
    expect(await screen.findByText('Дневная')).toBeInTheDocument()
    expect(screen.getByText('Всего шаблонов').previousElementSibling).toHaveTextContent('2')
    expect(screen.getByText('Авто-создание').previousElementSibling).toHaveTextContent('1')
    expect(screen.getByText('Активных шаблонов').previousElementSibling).toHaveTextContent('1')

    const day = screen.getByText('Дневная').closest('tr') as HTMLElement
    expect(within(day).getByText('Будни')).toBeInTheDocument()
    expect(within(day).getByText(/08:00 — 17:00/)).toBeInTheDocument()
    expect(within(day).getByText('Обычная')).toBeInTheDocument()
    expect(within(day).getByText('Пн')).toHaveClass('text-accent')
    expect(within(day).getByText('Сб')).toHaveClass('text-text-muted')
    expect(within(day).getByText('1—4')).toBeInTheDocument()
    expect(within(day).getByTitle('Авто-создание включено')).toBeInTheDocument()
    expect(within(day).getByRole('button', { name: 'Создать' })).toBeInTheDocument()

    const night = screen.getByText('Ночная').closest('tr') as HTMLElement
    expect(within(night).getByText(/22:30 — 06:30/)).toBeInTheDocument()
    expect(within(night).getByText('+1д')).toBeInTheDocument()
    expect(within(night).getByText('Экстренная')).toBeInTheDocument()
    expect(within(night).getByText('Цикл 2/2 (с 01.09)')).toBeInTheDocument()
    expect(within(night).getByText('—')).toBeInTheDocument() // без спец-ций
    expect(within(night).queryByRole('button', { name: 'Создать' })).not.toBeInTheDocument() // неактивный
    expect(night).toHaveClass('opacity-50')
  })

  it('тумблер авто → PATCH; «Удал.» → подтверждение → DELETE; «Ред.» открывает модалку с шаблоном; «Создать» — модалку смены', async () => {
    const user = userEvent.setup()
    render(<TemplatesPage />)
    const day = (await screen.findByText('Дневная')).closest('tr') as HTMLElement

    await user.click(within(day).getByTitle('Авто-создание включено'))
    await waitFor(() => expect(patches).toEqual([{ id: '1', body: { auto_create: false } }]))

    await user.click(within(day).getByRole('button', { name: 'Удал.' }))
    expect(await screen.findByText('Удалить шаблон')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Удалить' }))
    await waitFor(() => expect(deletes).toEqual(['1']))

    await user.click(within(day).getByRole('button', { name: 'Ред.' }))
    expect(within(await screen.findByRole('dialog')).getByDisplayValue('Дневная')).toBeInTheDocument()
    await user.keyboard('{Escape}')

    await user.click(within(day).getByRole('button', { name: 'Создать' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('пустой список — заглушка; ошибка загрузки — текст', async () => {
    server.use(http.get('*/api/v2/shifts/templates', () => HttpResponse.json([])))
    const { unmount } = render(<TemplatesPage />)
    expect(await screen.findByText('Нет шаблонов')).toBeInTheDocument()
    unmount()
    server.use(http.get('*/api/v2/shifts/templates', () => HttpResponse.json({ detail: 'x' }, { status: 500 })))
    render(<TemplatesPage />)
    expect(await screen.findByText(/Ошибка загрузки шаблонов/)).toBeInTheDocument()
  })
})
