import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { vi, it, expect } from 'vitest'
import { apiClient } from '@/api/client'
import '@/i18n'
import ApartmentPaymentBlock from './ApartmentPaymentBlock'

function mount(accountNumber: string | null = '001') {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><ApartmentPaymentBlock apartmentId={1} accountNumber={accountNumber} /></MemoryRouter>
  </QueryClientProvider>)
}

it('shows dated debt, prepayment and the exact account link', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: { status: 'available', account_number: '001', current: { debt: '120.50', prepayment: '0.00', as_of: '2026-09-01', source: 'Accounting', import_id: 9, line: 2, filename: 'debt.xlsx', currency: 'UZS' } } })
  mount()
  expect(await screen.findByText(/120.50/)).toBeInTheDocument()
  expect(screen.getByText(/2026-09-01/)).toBeInTheDocument()
  expect(screen.getByRole('link').getAttribute('href')).toBe('/dashboard/payment-control?account=001&import=9&offset=0')
})

it('never substitutes zero for unavailable service', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: { status: 'unavailable', current: null } })
  mount()
  expect(await screen.findByText(/Сервис контроля платежей недоступен/)).toBeInTheDocument()
  expect(screen.queryByText(/0.00/)).not.toBeInTheDocument()
})

it('does not fetch without an account', async () => {
  const get = vi.spyOn(apiClient, 'get')
  get.mockClear()
  mount(null)
  expect(screen.getByText(/Укажите лицевой счёт/)).toBeInTheDocument()
  expect(get).not.toHaveBeenCalled()
})

it('renders the Uzbek locale for every state, not just Russian', async () => {
  const i18n = (await import('@/i18n')).default
  await i18n.changeLanguage('uz')
  try {
    mount(null)
    expect(screen.getByText(/Xonadon sozlamalarida shaxsiy hisob raqamini kiriting/)).toBeInTheDocument()
    cleanup()
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: { status: 'unavailable', current: null } })
    mount()
    expect(await screen.findByText(/To‘lovlar nazorati xizmati mavjud emas/)).toBeInTheDocument()
  } finally {
    await i18n.changeLanguage('ru')
  }
})

it('refetches the balance once a minute so a fresh import is not missed', async () => {
  vi.useFakeTimers()
  try {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { status: 'no_data', account_number: '001', current: null } })
    mount()
    await vi.advanceTimersByTimeAsync(61_000)
    expect(get.mock.calls.length).toBeGreaterThan(1)
  } finally {
    vi.useRealTimers()
  }
})
