import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { ReactNode } from 'react'
import { http, HttpResponse } from 'msw'
import { act, fireEvent, render, screen, waitFor, within } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import KanbanBoard from './KanbanBoard'
import type { RequestCard as TCard } from '../../hooks/useKanban'

// TEST-068: доска канбана. dnd-kit подменён тонкой обёрткой: тест дёргает
// onDragStart/onDragOver/onDragEnd напрямую с синтетическими событиями, а
// логика доски (правила переходов, модалки, optimistic PATCH, баннер ошибки)
// работает по-настоящему — колонки из msw, PATCH в msw.

type DragHandlers = {
  onDragStart?: (e: { active: { id: string } }) => void
  onDragOver?: (e: { over: { id: string } | null }) => void
  onDragEnd?: (e: { active: { id: string }; over: { id: string } | null }) => void
}
const dnd = vi.hoisted(() => ({ handlers: {} as DragHandlers }))

// useKanban поднимает WebSocket; без стаба msw ругается на неперехваченное соединение.
class FakeWebSocket {
  onclose: unknown = null
  onmessage: unknown = null
  onopen: unknown = null
  readyState = 0
  close() {}
}

vi.mock('@dnd-kit/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@dnd-kit/core')>()
  return {
    ...actual,
    DndContext: ({ children, onDragStart, onDragOver, onDragEnd }: DragHandlers & { children: ReactNode }) => {
      dnd.handlers = { onDragStart, onDragOver, onDragEnd }
      return <>{children}</>
    },
    DragOverlay: ({ children }: { children: ReactNode }) => <div data-testid="drag-overlay">{children}</div>,
  }
})

function card(request_number: string, status: string, over: Partial<TCard> = {}): TCard {
  return {
    request_number,
    status,
    category: 'electricity',
    urgency: 'medium',
    source: 'web',
    description: `Описание ${request_number}`,
    address: 'ул. Ленина, 1',
    executor_id: null,
    executor_name: null,
    notes: null,
    completion_report: null,
    requested_materials: null,
    return_reason: null,
    manager_return_reason: null,
    created_at: '2026-09-18T08:00:00Z',
    updated_at: null,
    manager_confirmed: false,
    elevator_id: null,
    elevator_label: null,
    elevator_status: null,
    ...over,
  }
}

const COLUMNS = [
  { status: 'Новая', count: 2, requests: [card('N-1', 'Новая'), card('N-2', 'Новая', { executor_id: 7, executor_name: 'Иван' })] },
  { status: 'В работе', count: 1, requests: [card('W-1', 'В работе', { executor_id: 7 })] },
  { status: 'Закуп', count: 1, requests: [card('P-1', 'Закуп', { executor_id: 7 })] },
  { status: 'Уточнение', count: 1, requests: [card('C-1', 'Уточнение', { executor_id: 7, updated_at: '2026-09-18T09:00:00Z' })] },
  { status: 'Выполнена', count: 1, requests: [card('D-1', 'Выполнена', { executor_id: 7 })] },
  { status: 'Отменена', count: 0, requests: [] },
]

let patches: Array<{ number: string; body: Record<string, unknown> }>
let patchResponse: () => Response
/** Сервер помнит переходы: после успешного PATCH refetch отдаёт карточку в новой колонке. */
let served: typeof COLUMNS

function moveServed(number: string, status: string) {
  const moving = served.flatMap((c) => c.requests).find((r) => r.request_number === number)
  if (!moving) return
  served = served.map((c) => ({
    ...c,
    requests: c.status === status
      ? [...c.requests.filter((r) => r.request_number !== number), { ...moving, status }]
      : c.requests.filter((r) => r.request_number !== number),
  })).map((c) => ({ ...c, count: c.requests.length }))
}

function installHandlers() {
  server.use(
    http.get('*/api/v2/requests/kanban', () => HttpResponse.json({ columns: served })),
    http.get('*/api/v2/shifts/employees', () => HttpResponse.json([])),
    http.patch('*/api/v2/requests/:number', async ({ params, request }) => {
      const body = (await request.json()) as Record<string, unknown>
      patches.push({ number: String(params.number), body })
      const res = patchResponse()
      if (res.ok) moveServed(String(params.number), String(body.status))
      return res
    }),
  )
}

async function renderBoard(onCardClick = vi.fn()) {
  render(<KanbanBoard onCardClick={onCardClick} />)
  await waitFor(() => expect(screen.getByText('N-1')).toBeInTheDocument())
  return onCardClick
}

const drag = {
  start: (id: string) => act(() => dnd.handlers.onDragStart?.({ active: { id } })),
  over: (id: string | null) => act(() => dnd.handlers.onDragOver?.({ over: id === null ? null : { id } })),
  end: (id: string, overId: string | null) =>
    act(() => dnd.handlers.onDragEnd?.({ active: { id }, over: overId === null ? null : { id: overId } })),
}

beforeEach(() => {
  patches = []
  patchResponse = () => HttpResponse.json({ ok: true })
  served = JSON.parse(JSON.stringify(COLUMNS))
  dnd.handlers = {}
  localStorage.clear()
  vi.stubGlobal('WebSocket', FakeWebSocket)
  // В jsdom нет PointerEvent: fireEvent.pointerUp собрал бы голый Event без clientX.
  vi.stubGlobal('PointerEvent', MouseEvent)
  installHandlers()
})

describe('KanbanBoard — рендер', () => {
  it('загрузка → колонки со счётчиками и карточками; непрочитанное только в «Уточнение»', async () => {
    render(<KanbanBoard onCardClick={() => {}} />)
    expect(screen.getByText('Загрузка...')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('N-1')).toBeInTheDocument())
    for (const label of ['Новая', 'В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Отменена']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getByText('Нет заявок')).toBeInTheDocument() // пустая «Отменена»
    // Непрочитанное отслеживается только в «Уточнение» и «Закуп» — два бейджа,
    // у «Новая» (там тоже есть свежие карточки) бейджа нет.
    expect(screen.getAllByTestId('unread-count')).toHaveLength(2)
    const newCol = screen.getByText('Новая').closest('.rounded-\\[14px\\]') as HTMLElement
    expect(within(newCol).queryByTestId('unread-count')).toBeNull()
  })

  it('ошибка загрузки → «Ошибка»', async () => {
    server.use(http.get('*/api/v2/requests/kanban', () => HttpResponse.json({ detail: 'x' }, { status: 500 })))
    render(<KanbanBoard onCardClick={() => {}} />)
    expect(await screen.findByText('Ошибка')).toBeInTheDocument()
  })
})

describe('KanbanBoard — перетаскивание', () => {
  it('start показывает карточку в оверлее, over подсвечивает допустимую колонку, end сбрасывает', async () => {
    await renderBoard()
    await drag.start('N-1')
    expect(within(screen.getByTestId('drag-overlay')).getByText('N-1')).toBeInTheDocument()
    await drag.over('В работе')
    const col = screen.getByText('В работе').closest('.rounded-\\[14px\\]') as HTMLElement
    expect(col.className).toContain('scale-[1.01]')
    await drag.over(null)
    expect(col.className).not.toContain('scale-[1.01]')
    await drag.end('N-1', null)
    expect(within(screen.getByTestId('drag-overlay')).queryByText('N-1')).toBeNull()
    expect(patches).toHaveLength(0)
  })

  it('Новая → Отменена (без модалки): PATCH status, optimistic-перенос карточки', async () => {
    await renderBoard()
    await drag.end('N-1', 'Отменена')
    await waitFor(() => expect(patches).toEqual([{ number: 'N-1', body: { status: 'Отменена' } }]))
    // Optimistic-перенос, затем refetch с сервера — карточка в «Отменена», пустышка ушла.
    await waitFor(() => expect(screen.queryByText('Нет заявок')).toBeNull())
    const cancelled = screen.getByText('Отменена').closest('.rounded-\\[14px\\]') as HTMLElement
    expect(within(cancelled).getByText('N-1')).toBeInTheDocument()
  })

  it('недопустимый переход, drop на себя и over=null — PATCH нет', async () => {
    await renderBoard()
    await drag.end('W-1', 'Новая') // В работе → Новая запрещён
    await drag.end('N-1', 'N-1')
    await drag.end('N-1', null)
    await drag.end('P-1', 'Выполнена') // Закуп → Выполнена запрещён
    expect(patches).toHaveLength(0)
  })

  it('Новая без исполнителя → В работе (drop на карточку колонки): модалка исполнителя; отмена — без PATCH', async () => {
    await renderBoard()
    await drag.end('N-1', 'W-1') // over = карточка в «В работе» → целевая колонка «В работе»
    expect(await screen.findByText('Назначить исполнителя')).toBeInTheDocument()
    act(() => screen.getByRole('button', { name: 'Отмена' }).click())
    await waitFor(() => expect(screen.queryByText('Назначить исполнителя')).toBeNull())
    expect(patches).toHaveLength(0)
  })

  it('Новая с исполнителем и Закуп → В работе коммитятся напрямую (без executor_id)', async () => {
    await renderBoard()
    await drag.end('N-2', 'В работе')
    await drag.end('P-1', 'В работе')
    await waitFor(() => expect(patches).toHaveLength(2))
    expect(patches.map((p) => [p.number, p.body])).toEqual([
      ['N-2', { status: 'В работе' }],
      ['P-1', { status: 'В работе' }],
    ])
    expect(screen.queryByText('Назначить исполнителя')).toBeNull()
  })

  it('Выполнена → В работе: модалка причины, подтверждение шлёт return_reason', async () => {
    await renderBoard()
    await drag.end('D-1', 'В работе')
    expect(await screen.findByText('Вернуть в работу')).toBeInTheDocument()
    const confirm = screen.getByRole('button', { name: 'Подтвердить' })
    expect(confirm).toBeDisabled()
    const area = screen.getByPlaceholderText('Что нужно переделать? Исполнитель увидит этот текст')
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
      setter?.call(area, 'Не закреплён кабель')
      area.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await waitFor(() => expect(confirm).toBeEnabled())
    act(() => confirm.click())
    await waitFor(() => expect(patches).toEqual([{ number: 'D-1', body: { status: 'В работе', return_reason: 'Не закреплён кабель' } }]))
    await waitFor(() => expect(screen.queryByText('Вернуть в работу')).toBeNull())
  })

  it('Новая → Закуп: модалка «Что необходимо купить?», подтверждение шлёт requested_materials', async () => {
    await renderBoard()
    await drag.end('N-1', 'Закуп')
    expect(await screen.findByText('Что необходимо купить?')).toBeInTheDocument()
    const area = screen.getByPlaceholderText(/труба ПВХ/)
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
      setter?.call(area, 'Кабель 10 м')
      area.dispatchEvent(new Event('input', { bubbles: true }))
    })
    const confirm = screen.getByRole('button', { name: 'Подтвердить' })
    await waitFor(() => expect(confirm).toBeEnabled())
    act(() => confirm.click())
    await waitFor(() => expect(patches).toEqual([{ number: 'N-1', body: { status: 'Закуп', requested_materials: 'Кабель 10 м' } }]))
  })

  it('ошибка PATCH: баннер с текстом сервера, без detail — общий текст', async () => {
    patchResponse = () => HttpResponse.json({ detail: 'Нет дежурного на смене' }, { status: 409 })
    await renderBoard()
    await drag.end('N-1', 'Отменена')
    expect(await screen.findByText('Нет дежурного на смене')).toBeInTheDocument()

    patchResponse = () => HttpResponse.json({}, { status: 500 })
    await drag.end('N-2', 'Отменена')
    expect(await screen.findByText('Не удалось сохранить изменение. Попробуйте снова.')).toBeInTheDocument()
  })

  it('клик по карточке отдаёт номер наверх', async () => {
    const onCardClick = await renderBoard()
    // Клик = pointerdown/up почти без смещения (иначе это начало drag).
    const el = screen.getByText('N-1')
    fireEvent.pointerDown(el, { clientX: 10, clientY: 10 })
    fireEvent.pointerUp(el, { clientX: 12, clientY: 11 })
    expect(onCardClick).toHaveBeenCalledWith('N-1')
    fireEvent.pointerDown(el, { clientX: 10, clientY: 10 })
    fireEvent.pointerUp(el, { clientX: 40, clientY: 10 })
    expect(onCardClick).toHaveBeenCalledTimes(1) // сдвиг ≥ 5px — не клик
  })
})
