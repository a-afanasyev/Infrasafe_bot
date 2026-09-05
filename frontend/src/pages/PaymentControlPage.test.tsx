import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import '@/i18n'
import PaymentControlPage from './PaymentControlPage'
import { formatBusinessDate } from '../components/payment/format'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('uploads a preview then activates only after a separate confirmation', async () => {
  const report = { id: 5, kind: 'balances', source: 'Accounting', filename: 'balances.csv', as_of: '2026-09-01', status: 'preview', invalid: 0, row_count: 1, rows: [{ line: 2, account_number: '001', debt: '120.00', prepayment: '0.00', errors: [] }], audit: [] }
  vi.spyOn(apiClient, 'get').mockImplementation(async url => ({ data: url.endsWith('/imports/5') ? report : [report] }))
  const post = vi.spyOn(apiClient, 'post').mockImplementation(async url => {
    if (url.endsWith('/activate')) report.status = 'active'
    return { data: { ...report } }
  })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><PaymentControlPage /></MemoryRouter></QueryClientProvider>)
  const user = userEvent.setup()
  await user.upload(screen.getByLabelText('CSV / XLSX'), new File(['account_number;debt;prepayment\n001;120;0'], 'balances.csv', { type: 'text/csv' }))
  await user.click(screen.getByRole('button', { name: 'Проверить файл' }))
  const activate = await screen.findByRole('button', { name: 'Подтвердить и активировать' })
  expect(post).toHaveBeenCalledTimes(1)
  expect(post.mock.calls[0][1]).toBeInstanceOf(FormData)
  await user.click(activate)
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v2/payment-control/imports/5/activate', undefined))
  expect(await screen.findByRole('button', { name: 'Деактивировать' })).toBeDisabled()
})

it('blocks activation for an invalid import and shows row errors', async () => {
  const report = { id: 3, kind: 'balances', source: 'Accounting', filename: 'bad.csv', as_of: '2026-09-01', status: 'preview', invalid: 1, row_count: 1, rows: [{ line: 2, account_number: '001', errors: ['Некорректная сумма'] }] }
  vi.spyOn(apiClient, 'get').mockImplementation(async url => ({ data: url.includes('/imports/3') ? report : [report] }))
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={['/?import=3']}><PaymentControlPage /></MemoryRouter></QueryClientProvider>)
  expect(await screen.findByRole('button', { name: 'Подтвердить и активировать' })).toBeDisabled()
  expect(screen.getByText('Некорректная сумма')).toBeInTheDocument()
})

it('searches an account, opens its source and deactivates with a reason', async () => {
  const report = { id: 7, kind: 'balances', source: 'Accounting', filename: 'debt.xlsx', as_of: '2026-09-01', status: 'active', invalid: 0, row_count: 201,
    rows: [{ line: 2, account_number: '001', debt: '0.00', prepayment: '50.00', errors: [] }],
    audit: [{ action: 'activate', actor_id: '7', created_at: '2026-09-01', reason: 'Проверено' }] }
  const snapshot = { debt: '0.00', prepayment: '50.00', as_of: '2026-09-01', source: 'Accounting', filename: 'debt.xlsx', import_id: 7, line: 2, position: 0 }
  const get = vi.spyOn(apiClient, 'get').mockImplementation(async url => ({ data: url.endsWith('/account')
    ? { status: 'available', account_number: '001', current: snapshot, history: [snapshot], payments: [{ operation_id: 'bank-1', paid_at: '2026-09-01', amount: '50.00', source: 'Bank', import_id: 7 }] }
    : url.endsWith('/imports/7') ? report : Array.from({ length: 50 }, (_, i) => ({ ...report, id: i + 1 })) }))
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: report })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><PaymentControlPage /></MemoryRouter></QueryClientProvider>)
  const user = userEvent.setup()
  await user.type(screen.getByRole('textbox', { name: 'Лицевой счёт' }), '001')
  await user.click(screen.getByRole('button', { name: 'Найти', exact: true }))
  await user.click(await screen.findByRole('button', { name: 'debt.xlsx · Строка 2' }))
  expect(await screen.findByRole('button', { name: 'Деактивировать' })).toBeDisabled()
  await user.click(screen.getByText('История активных снимков (до 50)'))
  await user.click(screen.getByRole('button', { name: `${formatBusinessDate('2026-09-01')} · Accounting` }))
  await user.click(screen.getByText('Платежи', { selector: 'summary' }))
  await user.click(screen.getByRole('button', { name: 'Bank', exact: true }))
  await user.click(screen.getByText('История действий'))
  expect(screen.getByText(/Проверено/)).toBeInTheDocument()
  await user.click(screen.getAllByRole('button', { name: 'Далее', exact: true })[0])
  await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v2/payment-control/imports/7', { params: { offset: 200 } }))
  await user.click(screen.getAllByRole('button', { name: 'Назад', exact: true })[0])
  await user.type(screen.getByRole('textbox', { name: 'Причина деактивации' }), '  Ошибочная выгрузка  ')
  await user.click(screen.getByRole('button', { name: 'Деактивировать' }))
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v2/payment-control/imports/7/deactivate', { reason: 'Ошибочная выгрузка' }))
  await user.click(screen.getByRole('button', { name: 'Обновить' }))
  await user.click(screen.getAllByRole('button', { name: 'Далее', exact: true })[1])
  await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v2/payment-control/imports', { params: { offset: 50 } }))
  await user.click(screen.getAllByRole('button', { name: 'Назад', exact: true })[1])
  await user.clear(screen.getByLabelText('Источник'))
  await user.type(screen.getByLabelText('Источник'), 'Bank')
  await user.selectOptions(screen.getByLabelText('Тип данных'), 'payments')
  expect(screen.getByText('account_number;operation_id;paid_at;amount')).toBeInTheDocument()
})

it('reports service errors without rendering an invented balance', async () => {
  vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('Offline'))
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/?account=001&import=9']}><PaymentControlPage /></MemoryRouter></QueryClientProvider>)
  expect((await screen.findAllByText('Сервис контроля платежей недоступен. Суммы не подтверждены.')).length).toBeGreaterThan(0)
  expect(screen.queryByText(/0\.00\s*UZS/)).not.toBeInTheDocument()
})

// ── Правки по итогам ревью ───────────────────────────────────────────────────

function mountPage(entries = ['/']) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={entries}><PaymentControlPage /></MemoryRouter>
  </QueryClientProvider>)
}

it('ставит заголовок документа', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] })
  mountPage()
  await waitFor(() => expect(document.title).toMatch(/Контроль платежей/))
})

it('дата состояния по умолчанию — календарное сегодня в бизнес-зоне, не UTC', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] })
  const { todayInDisplayTz } = await import('../utils/timezone')
  mountPage()
  expect(screen.getByLabelText('Данные на дату')).toHaveValue(todayInDisplayTz())
})

it('отказ по данным (422) показывает сообщение проверки, а не «сервис недоступен»', async () => {
  const rejection = Object.assign(new Error('Request failed'), {
    isAxiosError: true,
    response: { status: 422, data: { detail: 'Некорректный лицевой счёт' } },
  })
  vi.spyOn(apiClient, 'get').mockImplementation(async url =>
    url.endsWith('/account') ? Promise.reject(rejection) : { data: [] })
  mountPage(['/?account=..bad'])
  expect(await screen.findByText('Некорректный лицевой счёт')).toBeInTheDocument()
  expect(screen.queryByText('Сервис контроля платежей недоступен. Суммы не подтверждены.')).not.toBeInTheDocument()
})

it('подсвечивает строку искомого лицевого счёта в предпросмотре', async () => {
  const report = { id: 4, kind: 'balances', source: 'Accounting', filename: 'balances.csv', as_of: '2026-09-01',
    status: 'preview', invalid: 0, row_count: 2, audit: [],
    rows: [{ line: 2, account_number: '001', debt: '10.00', prepayment: '0.00', errors: [] },
           { line: 3, account_number: '002', debt: '20.00', prepayment: '0.00', errors: [] }] }
  vi.spyOn(apiClient, 'get').mockImplementation(async url => ({
    data: url.includes('/imports/4') ? report : url.endsWith('/account') ? { status: 'no_data', account_number: '002', current: null } : [report],
  }))
  mountPage(['/?import=4&account=002'])
  const marked = await screen.findByText('002')
  expect(marked.closest('tr')).toHaveClass('bg-accent/10')
  expect(screen.getByText('001').closest('tr')).not.toHaveClass('bg-accent/10')
})
