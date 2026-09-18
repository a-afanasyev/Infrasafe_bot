import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import type { MaterialCard, OperationRow } from '../../types/materials'
import ReceiptDialog from './ReceiptDialog'
import IssueDialog from './IssueDialog'
import AdjustmentDialog from './AdjustmentDialog'
import ReversalDialog from './ReversalDialog'
import MaterialSelect from './MaterialSelect'

// TEST-068 (порция materials): диалоги движений склада. Общий селект
// номенклатуры грузит GET /materials?is_active=true&limit=200 (msw).

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const MATERIALS: MaterialCard[] = [
  { id: 1, name: 'Лампа', unit: 'pcs', category: null, min_stock: null, is_active: true, created_at: null },
  { id: 2, name: 'Кабель', unit: 'm', category: 'Электрика', min_stock: '10', is_active: true, created_at: null },
]

beforeEach(() => {
  vi.mocked(toast.success).mockClear()
  server.use(http.get('*/api/v2/materials', ({ request }) => {
    const url = new URL(request.url)
    expect(url.searchParams.get('is_active')).toBe('true')
    expect(url.searchParams.get('limit')).toBe('200')
    return HttpResponse.json(MATERIALS)
  }))
})

/** Селект номенклатуры грузится асинхронно — ждём опцию, потом выбираем. */
async function pickMaterial(user: ReturnType<typeof userEvent.setup>, value: string, index = 0) {
  await screen.findByRole('option', { name: 'Лампа (шт)' })
  await user.selectOptions(screen.getAllByRole('combobox')[index], value)
}

function captured(path: string, status = 201) {
  const bodies: Record<string, unknown>[] = []
  server.use(http.post(`*/api/v2/materials/${path}`, async ({ request }) => {
    bodies.push((await request.json()) as Record<string, unknown>)
    return HttpResponse.json({ ok: true }, { status })
  }))
  return bodies
}

describe('MaterialSelect', () => {
  it('показывает активную номенклатуру с единицами и отдаёт число / пустую строку', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<MaterialSelect value="" onChange={onChange} />)

    expect(await screen.findByRole('option', { name: 'Лампа (шт)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Кабель (м)' })).toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox'), '2')
    expect(onChange).toHaveBeenLastCalledWith(2)
    await user.selectOptions(screen.getByRole('combobox'), '')
    expect(onChange).toHaveBeenLastCalledWith('')
  })
})

describe('ReceiptDialog', () => {
  it('«Оприходовать» доступна только с материалом, qty > 0 и ценой ≥ 0; POST /receipts без пустых полей', async () => {
    const user = userEvent.setup()
    const bodies = captured('receipts')
    const onClose = vi.fn()
    render(<ReceiptDialog open onClose={onClose} />)
    const submit = screen.getByRole('button', { name: 'Оприходовать' })
    expect(submit).toBeDisabled()

    await pickMaterial(user, '1')
    const [qty, price] = screen.getAllByRole('spinbutton')
    await user.type(qty, '5')
    expect(submit).toBeEnabled() // пустая цена читается как 0 ≥ 0 — бесплатный приход допустим
    await user.type(price, '0')
    expect(submit).toBeEnabled()
    await user.click(submit)

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(bodies).toEqual([{ material_id: 1, qty: '5', unit_price: '0' }])
    expect(toast.success).toHaveBeenCalledWith('Приход проведён')
  })

  it('поставщик, документ и дата попадают в тело; сбой сервера не закрывает диалог', async () => {
    const user = userEvent.setup()
    const bodies = captured('receipts', 422)
    const onClose = vi.fn()
    render(<ReceiptDialog open onClose={onClose} />)

    await pickMaterial(user, '2')
    const [qty, price] = screen.getAllByRole('spinbutton')
    await user.type(qty, '12.5')
    await user.type(price, '1000')
    const [supplier, docNumber] = screen.getAllByRole('textbox')
    await user.type(supplier, ' ООО Свет ')
    await user.type(docNumber, 'ТН-17')
    await user.click(screen.getByRole('button', { name: 'Оприходовать' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(onClose).not.toHaveBeenCalled()
    expect(bodies[0]).toMatchObject({ material_id: 2, qty: '12.5', unit_price: '1000', supplier: 'ООО Свет', doc_number: 'ТН-17' })
    expect(bodies[0]).not.toHaveProperty('doc_date')
  })
})

describe('IssueDialog', () => {
  it('«На заявку»: нужен номер заявки; POST /issues c doc_type=request без reason', async () => {
    const user = userEvent.setup()
    const bodies = captured('issues')
    const onClose = vi.fn()
    render(<IssueDialog open onClose={onClose} />)
    const submit = screen.getByRole('button', { name: 'Списать' })

    await pickMaterial(user, '1')
    await user.type(screen.getByRole('spinbutton'), '2')
    expect(submit).toBeDisabled()
    await user.type(screen.getByPlaceholderText('260705-001'), ' 260918-001 ')
    expect(submit).toBeEnabled()
    await user.click(submit)

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(bodies).toEqual([{ material_id: 1, qty: '2', doc_type: 'request', request_number: '260918-001' }])
    expect(toast.success).toHaveBeenCalledWith('Расход проведён')
  })

  it('«Хознужды»: поле причины вместо номера; doc_type=household', async () => {
    const user = userEvent.setup()
    const bodies = captured('issues')
    render(<IssueDialog open onClose={() => {}} />)

    await pickMaterial(user, '2')
    await user.selectOptions(screen.getAllByRole('combobox')[1], 'household')
    expect(screen.queryByPlaceholderText('260705-001')).not.toBeInTheDocument()
    await user.type(screen.getByRole('spinbutton'), '3')
    await user.type(screen.getByRole('textbox'), 'Уборка двора')
    await user.click(screen.getByRole('button', { name: 'Списать' }))

    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({ material_id: 2, qty: '3', doc_type: 'household', reason: 'Уборка двора' })
  })
})

describe('AdjustmentDialog', () => {
  it('излишек: цена уходит в тело; недостача: поле цены скрыто, цена не передаётся', async () => {
    const user = userEvent.setup()
    const bodies = captured('adjustments')
    const onClose = vi.fn()
    render(<AdjustmentDialog open onClose={onClose} />)
    expect(screen.getByText('Излишек оприходуется партией, недостача списывается по FIFO')).toBeInTheDocument()

    await pickMaterial(user, '1')
    const direction = screen.getAllByRole('combobox')[1]
    expect(screen.getAllByRole('spinbutton')).toHaveLength(2) // qty + цена (излишек)
    const [qty, price] = screen.getAllByRole('spinbutton')
    await user.type(qty, '4')
    await user.type(price, '250')
    const submit = screen.getByRole('button', { name: 'Провести' })
    expect(submit).toBeDisabled() // причина обязательна
    await user.type(screen.getByRole('textbox'), 'Пересчёт')
    await user.click(submit)
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(bodies[0]).toEqual({ material_id: 1, direction: 'surplus', qty: '4', unit_price: '250', reason: 'Пересчёт' })

    await user.selectOptions(direction, 'shortage')
    expect(screen.getAllByRole('spinbutton')).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Провести' }))
    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies[1]).toEqual({ material_id: 1, direction: 'shortage', qty: '4', reason: 'Пересчёт' })
    expect(toast.success).toHaveBeenCalledWith('Корректировка проведена')
  })
})

describe('ReversalDialog', () => {
  const ISSUE: OperationRow = {
    op_type: 'issue', id: 55, material_id: 1, material_name: 'Лампа', unit: 'pcs', doc_type: 'request',
    qty: '10.500', amount: '5250.00', request_number: '260918-001', supplier: null, reason: null,
    created_by: 1, created_at: null,
  }

  it('без операции ничего не рендерит', () => {
    const { container } = render(<ReversalDialog operation={null} onClose={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('сторно расхода: заголовок, сводка, direction=surplus и reversal_of_issue_id', async () => {
    const user = userEvent.setup()
    const bodies = captured('adjustments')
    const onClose = vi.fn()
    render(<ReversalDialog operation={ISSUE} onClose={onClose} />)

    expect(screen.getByText('Сторно расхода')).toBeInTheDocument()
    expect(screen.getByText(/Лампа — 10,5 шт\./)).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: 'Сторнировать' })
    expect(submit).toBeDisabled()
    await user.type(screen.getByRole('textbox'), 'Ошибочное списание')
    await user.click(submit)

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(bodies).toEqual([{ material_id: 1, direction: 'surplus', reason: 'Ошибочное списание', reversal_of_issue_id: 55 }])
  })

  it('сторно прихода: direction=shortage и reversal_of_receipt_id', async () => {
    const user = userEvent.setup()
    const bodies = captured('adjustments')
    render(<ReversalDialog operation={{ ...ISSUE, op_type: 'receipt', id: 9, doc_type: 'purchase' }} onClose={() => {}} />)

    expect(screen.getByText('Сторно прихода')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox'), 'Дубль накладной')
    await user.click(screen.getByRole('button', { name: 'Сторнировать' }))

    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({ material_id: 1, direction: 'shortage', reason: 'Дубль накладной', reversal_of_receipt_id: 9 })
  })
})
