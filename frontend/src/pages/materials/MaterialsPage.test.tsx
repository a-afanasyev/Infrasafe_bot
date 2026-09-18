import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import type { MaterialCard, OperationRow, ProcurementOut, StockRow } from '../../types/materials'
import MaterialsPage from './MaterialsPage'

// TEST-068 (порция pages): «Склад материалов» — три вкладки на реальных
// хуках/msw: остатки с фильтрами и правкой карточки, журнал с фильтрами,
// сторно и пагинацией, «На закуп» с бейджем и открытыми заявками.

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const MATERIALS: MaterialCard[] = [
  { id: 1, name: 'Лампа', unit: 'pcs', category: 'Электрика', min_stock: '10', is_active: true, created_at: null },
  { id: 2, name: 'Кабель', unit: 'm', category: null, min_stock: null, is_active: true, created_at: null },
]
const STOCK: StockRow[] = [
  { material_id: 1, name: 'Лампа', unit: 'pcs', category: 'Электрика', min_stock: '10', stock: '4', stock_value: '1000.00', low_stock: true },
  { material_id: 2, name: 'Кабель', unit: 'm', category: null, min_stock: null, stock: '120.5', stock_value: '24100.00', low_stock: false },
]
const OP: OperationRow = {
  op_type: 'issue', id: 7, material_id: 1, material_name: 'Лампа', unit: 'pcs', doc_type: 'request', qty: '2',
  amount: '500.00', request_number: '260918-001', supplier: null, reason: null, created_by: 1, created_at: '2026-09-18T08:00:00Z',
}
const PROCUREMENT: ProcurementOut = {
  deficit: [{ material_id: 1, name: 'Лампа', unit: 'pcs', stock: '4', min_stock: '10', to_buy: '6' }],
  open_purchase_requests: [{ request_number: '260918-009', requested_materials: 'Лампы 10 шт', executor_name: 'Андрей Афанасьев' }],
}

let stockCalls: URLSearchParams[]
let opsCalls: URLSearchParams[]
let materialsCalls = 0

beforeEach(() => {
  useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: false })
  stockCalls = []; opsCalls = []; materialsCalls = 0
  server.use(
    http.get('*/api/v2/materials', () => { materialsCalls += 1; return HttpResponse.json(MATERIALS) }),
    http.get('*/api/v2/materials/stock', ({ request }) => { stockCalls.push(new URL(request.url).searchParams); return HttpResponse.json(STOCK) }),
    http.get('*/api/v2/materials/operations', ({ request }) => {
      const p = new URL(request.url).searchParams; opsCalls.push(p)
      return HttpResponse.json({ total: 120, items: p.get('offset') === '50' ? [] : [OP, { ...OP, op_type: 'receipt', id: 8, doc_type: 'surplus', supplier: 'ООО Свет', request_number: null }] })
    }),
    http.get('*/api/v2/materials/procurement', () => HttpResponse.json(PROCUREMENT)),
  )
})

describe('MaterialsPage — остатки', () => {
  it('таблица остатков: бейдж дефицита, форматы, фильтры уходят в запрос; карандаш открывает правку карточки', async () => {
    const user = userEvent.setup()
    render(<MaterialsPage />)
    expect(await screen.findByText('Склад материалов')).toBeInTheDocument()
    const lamp = (await screen.findByText('Лампа')).closest('tr') as HTMLElement
    expect(within(lamp).getByText('мало')).toBeInTheDocument()
    expect(within(lamp).getByText('шт')).toBeInTheDocument()
    expect(within(lamp).getByText('1 000,00')).toBeInTheDocument()
    const cable = screen.getByText('Кабель').closest('tr') as HTMLElement
    expect(within(cable).getByText('120,5')).toBeInTheDocument()
    expect(within(cable).getAllByText('—')).toHaveLength(2) // категория и мин. остаток
    expect(screen.getByRole('button', { name: /На закуп/ })).toHaveTextContent('1') // бейдж дефицита

    await user.type(screen.getByPlaceholderText('Поиск по названию…'), 'Лам')
    await user.click(screen.getByLabelText('Только дефицит'))
    await waitFor(() => expect(stockCalls.at(-1)?.get('only_low')).toBe('true'))
    expect(stockCalls.at(-1)?.get('q')).toBe('Лам')

    // карточка для правки берётся из GET /materials — дождаться ответа, потом клик
    await waitFor(() => expect(materialsCalls).toBeGreaterThan(0))
    // после смены фильтров строки перерисованы — старый `lamp` отсоединён от DOM, берём свежий
    const freshLamp = () => screen.getByText('Лампа').closest('tr') as HTMLElement
    await waitFor(async () => {
      await user.click(within(freshLamp()).getByTitle('Редактировать'))
      expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    }, { timeout: 3000 })
    const dialog = document.querySelector('[role="dialog"]') as HTMLElement
    expect(within(dialog).getAllByRole('textbox').some((el) => (el as HTMLInputElement).value === 'Лампа')).toBe(true)
    expect(within(dialog).getByRole('checkbox')).toBeChecked() // режим правки (is_active)
  })

  it('кнопки шапки открывают диалоги прихода/расхода/корректировки/новой карточки', async () => {
    const user = userEvent.setup()
    render(<MaterialsPage />)
    await screen.findByText('Склад материалов')
    await user.click(screen.getByRole('button', { name: /Приход/ }))
    expect(await screen.findByText('Приход материала')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    await user.click(screen.getByRole('button', { name: /Расход/ }))
    expect(await screen.findByText('Расход материала')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    await user.click(screen.getByRole('button', { name: /Корректировка/ }))
    expect(await screen.findByText('Корректировка (инвентаризация)')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    await user.click(screen.getByRole('button', { name: /Материал$/ }))
    expect(await screen.findByText('Новый материал')).toBeInTheDocument()
  })

  it('пустой склад — заглушка; ошибка API — текст ошибки', async () => {
    server.use(http.get('*/api/v2/materials/stock', () => HttpResponse.json([])))
    const { unmount } = render(<MaterialsPage />)
    expect(await screen.findByText('Материалы не найдены')).toBeInTheDocument()
    unmount()
    server.use(http.get('*/api/v2/materials/stock', () => HttpResponse.json({ detail: 'x' }, { status: 500 })))
    render(<MaterialsPage />)
    expect(await screen.findByText('Ошибка')).toBeInTheDocument()
  })
})

describe('MaterialsPage — журнал операций', () => {
  it('строки с типом/документом/деталями, фильтры сбрасывают offset, пагинация, сторно открывает диалог', async () => {
    const user = userEvent.setup()
    render(<MaterialsPage />)
    await screen.findByText('Склад материалов')
    await user.click(screen.getByRole('button', { name: 'Журнал операций' }))

    const rows = await screen.findAllByRole('row')
    expect(within(rows[1]).getByText('Расход')).toBeInTheDocument()
    expect(within(rows[1]).getByText('· по заявке')).toBeInTheDocument()
    expect(within(rows[1]).getByText('260918-001')).toBeInTheDocument()
    expect(within(rows[2]).getByText('· излишек/сторно')).toBeInTheDocument()
    expect(within(rows[2]).getByText('ООО Свет')).toBeInTheDocument()
    expect(within(rows[2]).queryByTitle('Сторно')).not.toBeInTheDocument() // surplus не сторнируется
    expect(screen.getByText('1–50 из 120')).toBeInTheDocument()

    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[0], 'issue')
    await user.selectOptions(selects[1], '1')
    await waitFor(() => expect(opsCalls.at(-1)?.get('op_type')).toBe('issue'))
    expect(opsCalls.at(-1)?.get('material_id')).toBe('1')
    expect(opsCalls.at(-1)?.get('offset')).toBe('0')

    await user.click(within(screen.getAllByRole('row')[1]).getByTitle('Сторно'))
    expect(await screen.findByText('Сторно расхода')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Отмена' }))

    expect(screen.getByRole('button', { name: '←' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '→' }))
    expect(await screen.findByText('Операций нет')).toBeInTheDocument()
    expect(opsCalls.at(-1)?.get('offset')).toBe('50')
  })
})

describe('MaterialsPage — на закуп', () => {
  it('дефицит с «Докупить», открытые заявки с deep-link и исполнителем; без дефицита — заглушка', async () => {
    const user = userEvent.setup()
    render(<MaterialsPage />)
    await screen.findByText('Склад материалов')
    await user.click(screen.getByRole('button', { name: /На закуп/ }))
    const row = (await screen.findByText('6')).closest('tr') as HTMLElement
    expect(within(row).getByText('Лампа')).toBeInTheDocument()
    expect(screen.getByText('Заявки в статусе «Закуп»')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '№260918-009' })).toHaveAttribute('href', '/dashboard?request=260918-009')
    expect(screen.getByText('Лампы 10 шт')).toBeInTheDocument()
    expect(screen.getByText(/Афанасьев/)).toBeInTheDocument()
  })

  it('без дефицита — заглушка и без бейджа на вкладке', async () => {
    server.use(http.get('*/api/v2/materials/procurement', () => HttpResponse.json({ deficit: [], open_purchase_requests: [] })))
    const user = userEvent.setup()
    render(<MaterialsPage />)
    await screen.findByText('Склад материалов')
    await user.click(screen.getByRole('button', { name: /На закуп/ }))
    expect(await screen.findByText('Дефицита нет — все остатки выше минимума')).toBeInTheDocument()
  })
})
