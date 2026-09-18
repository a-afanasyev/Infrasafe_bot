import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, fireEvent } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import ShiftDetailModal from './ShiftDetailModal'
import type { ShiftDetail } from '../../types/api'

// TEST-068: модалка смены — детали, метрики, действия по статусу/роли,
// завершение через подтверждение и переназначение (REG-02) на настоящих
// хуках + msw.

function detail(overrides: Partial<ShiftDetail> = {}): ShiftDetail {
  return {
    id: 5,
    user_id: 10,
    executor_name: 'Иван Тестов',
    status: 'active',
    shift_type: 'emergency',
    start_time: '2026-06-08T20:00:00+05:00',
    end_time: '2026-06-09T08:00:00+05:00',
    max_requests: 5,
    current_request_count: 3,
    load_percentage: 45,
    specialization_focus: null,
    coverage_areas: null,
    notes: 'Ключи у охраны',
    priority_level: 4,
    completed_requests: 7,
    efficiency_score: 0.8765,
    quality_rating: 4.5,
    template_id: null,
    created_at: null,
    ...overrides,
  }
}

const employees = [
  { id: 10, first_name: 'Иван', last_name: 'Тестов', phone: null, specialization: ['electrician'], active_shift_id: 5, verification_status: 'verified', status: 'approved', roles: ['executor'], bot_blocked: false },
  { id: 20, first_name: 'Пётр', last_name: 'Второй', phone: null, specialization: ['plumber'], active_shift_id: null, verification_status: 'verified', status: 'approved', roles: ['executor'], bot_blocked: false },
  { id: 30, first_name: 'Ожидающий', last_name: 'Кандидат', phone: null, specialization: [], active_shift_id: null, verification_status: 'pending', status: 'pending', roles: ['executor'], bot_blocked: false },
]

let posts: Array<{ url: string; body: unknown }>

function setRole(role: string) {
  useAuthStore.setState({ user: { id: 1, roles: [role] }, isAuthenticated: true, hydrating: false })
}

beforeEach(() => {
  posts = []
  server.use(
    http.get('*/api/v2/shifts/employees', () => HttpResponse.json(employees, { headers: { 'x-total-count': '3' } })),
    http.get('*/api/v2/shifts/5', () => HttpResponse.json(detail())),
    http.post('*/api/v2/shifts/5/end', () => { posts.push({ url: 'end', body: null }); return HttpResponse.json({ ok: true }) }),
    http.post('*/api/v2/shifts/5/reassign', async ({ request }) => {
      posts.push({ url: 'reassign', body: await request.json() })
      return HttpResponse.json({ ok: true })
    }),
  )
})
afterEach(() => useAuthStore.setState({ user: null, isAuthenticated: false }))

describe('ShiftDetailModal', () => {
  it('shiftId=null — ничего не рендерит', () => {
    render(<ShiftDetailModal shiftId={null} onClose={() => {}} />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('детали: заголовок, исполнитель, бейджи, диапазон с «+1д», метрики и заметки', async () => {
    setRole('executor')
    const onClose = vi.fn()
    render(<ShiftDetailModal shiftId={5} onClose={onClose} />)
    expect(await screen.findByText('Детали смены #5')).toBeInTheDocument()
    expect(await screen.findByText('Иван Тестов')).toBeInTheDocument()
    expect(screen.getByText('Экстренная')).toBeInTheDocument()
    expect(screen.getByText('Активна')).toBeInTheDocument()
    expect(screen.getByText(/20:00 — 08:00 \+1д/)).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
    expect(screen.getByText('4 / 5')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('3 / 5')).toBeInTheDocument()
    expect(screen.getByText('0.88')).toBeInTheDocument()
    expect(screen.getByText('4.5')).toBeInTheDocument()
    expect(screen.getByText('Ключи у охраны')).toBeInTheDocument()
    // Не менеджер: переназначения нет; onEdit не передан — «Редактировать» нет.
    expect(screen.queryByRole('button', { name: 'Переназначить' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Редактировать' })).toBeNull()
    // У Radix-диалога свой скрытый крестик с тем же именем — берём кнопку футера.
    fireEvent.click(screen.getAllByRole('button', { name: 'Закрыть' }).at(-1) as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('пустые метрики → прочерки; смена без конца → «в процессе»; исполнитель без имени → fallback', async () => {
    server.use(http.get('*/api/v2/shifts/5', () =>
      HttpResponse.json(detail({ efficiency_score: null, quality_rating: null, end_time: null, executor_name: null, notes: null, status: 'completed' })),
    ))
    render(<ShiftDetailModal shiftId={5} onClose={() => {}} />)
    expect(await screen.findByText('Исполнитель #10')).toBeInTheDocument()
    expect(screen.getAllByText('—')).toHaveLength(2)
    expect(screen.getByText(/— в процессе/)).toBeInTheDocument()
    expect(screen.queryByText('Заметки')).toBeNull()
    // Завершённая: ни завершить, ни завершить-кнопки.
    expect(screen.queryByRole('button', { name: 'Завершить смену' })).toBeNull()
  })

  it('«Завершить смену»: подтверждение → POST /shifts/5/end → onClose', async () => {
    const onClose = vi.fn()
    render(<ShiftDetailModal shiftId={5} onClose={onClose} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Завершить смену' }))
    expect(await screen.findByText('Завершить смену? Это действие нельзя отменить.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Завершить' }))
    await waitFor(() => expect(posts.map((p) => p.url)).toEqual(['end']))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('ошибка завершения → текст ошибки в модалке, onClose не вызван', async () => {
    server.use(http.post('*/api/v2/shifts/5/end', () => HttpResponse.json({ detail: 'nope' }, { status: 409 })))
    const onClose = vi.fn()
    render(<ShiftDetailModal shiftId={5} onClose={onClose} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Завершить смену' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Завершить' }))
    expect(await screen.findByText('Ошибка при завершении смены')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('менеджер: «Переназначить» показывает только approved-исполнителей без текущего; POST reassign → onClose', async () => {
    setRole('manager')
    const onClose = vi.fn()
    render(<ShiftDetailModal shiftId={5} onClose={onClose} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Переназначить' }))
    expect(await screen.findByText('Новый исполнитель')).toBeInTheDocument()

    const select = screen.getByRole('combobox') as HTMLSelectElement
    await waitFor(() => expect(select.options.length).toBe(2)) // плейсхолдер + Пётр
    expect(select.options[1]).toHaveTextContent('Пётр Второй (plumber)')
    expect(screen.queryByText(/Иван Тестов \(/)).toBeNull()
    expect(screen.queryByText(/Ожидающий/)).toBeNull()

    // Подтверждение (в блоке, он раньше футера в DOM) заблокировано, пока никто не выбран.
    const confirm = screen.getAllByRole('button', { name: 'Переназначить' })[0]
    expect(confirm).toBeDisabled()
    fireEvent.change(select, { target: { value: '20' } })
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)

    await waitFor(() => expect(posts).toEqual([{ url: 'reassign', body: { executor_id: 20 } }]))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('«Отмена» в блоке переназначения сворачивает его; «Редактировать» отдаёт смену в onEdit', async () => {
    setRole('manager')
    server.use(http.get('*/api/v2/shifts/5', () => HttpResponse.json(detail({ status: 'planned' }))))
    const onEdit = vi.fn()
    render(<ShiftDetailModal shiftId={5} onClose={() => {}} onEdit={onEdit} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Переназначить' }))
    expect(await screen.findByText('Новый исполнитель')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(screen.queryByText('Новый исполнитель')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Редактировать' }))
    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: 5, status: 'planned' }))
    // planned: завершать нечего.
    expect(screen.queryByRole('button', { name: 'Завершить смену' })).toBeNull()
  })

  it('смена не найдена → сообщение без действий', async () => {
    server.use(http.get('*/api/v2/shifts/5', () => HttpResponse.json({ detail: 'not found' }, { status: 404 })))
    render(<ShiftDetailModal shiftId={5} onClose={() => {}} />)
    expect(await screen.findByText('Смена не найдена')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Завершить смену' })).toBeNull()
    expect(screen.queryByText('Нагрузка')).toBeNull()
  })
})
