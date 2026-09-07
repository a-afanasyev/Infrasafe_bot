import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import '@/i18n'
import AddressTable from './AddressTable'
import type { ApartmentBrief, BuildingBrief } from '../../types/api'
import { formatBusinessDate } from '../payment/format'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllEnvs() })
// Сортировка запоминается в localStorage — без очистки соседние тесты
// наследовали бы чужой порядок строк.
beforeEach(() => { localStorage.clear(); vi.stubEnv('VITE_PAYMENTS_ENABLED', 'true') })

function apt(number: string, extra: Partial<ApartmentBrief> = {}): ApartmentBrief {
  return {
    id: Number(number.replace(/\D/g, '')) || 1,
    building_id: 1,
    apartment_number: number,
    building_address: 'Yangi Olmazor, 1G',
    yard_name: 'Olmazor City Phase 3',
    account_number: `13850000${number.padStart(2, '0')}`,
    entrance: 1,
    floor: 2,
    rooms_count: null,
    area: 52.02,
    description: null,
    is_active: true,
    created_at: null,
    residents_count: 0,
    ...extra,
  }
}

function mount(apartments: ApartmentBrief[]) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AddressTable level="apartments" apartments={apartments} />
    </QueryClientProvider>,
  )
}

function balancesReply(balances: Record<string, unknown>) {
  return vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { balances } })
}

it('нумерует строки по-человечески: 1, 2, 10, 100, а не 1, 10, 100, 2', async () => {
  balancesReply({})
  mount([apt('100'), apt('10'), apt('2'), apt('1')])
  const numbers = screen.getAllByText(/^(1|2|10|100)$/).map(el => el.textContent)
  expect(numbers).toEqual(['1', '2', '10', '100'])
})

it('дома тоже идут числовым порядком, а квартиры — внутри дома', async () => {
  balancesReply({})
  mount([
    apt('2', { id: 21, building_address: 'Yangi Olmazor, 10G' }),
    apt('10', { id: 12, building_address: 'Yangi Olmazor, 2G' }),
    apt('2', { id: 22, building_address: 'Yangi Olmazor, 2G' }),
  ])
  const houses = screen.getAllByTitle(/Yangi Olmazor/).map(el => el.textContent)
  expect(houses).toEqual(['2G', '2G', '10G'])
})

it('статус — только кружок с доступным именем, без подписи в каждой строке', async () => {
  balancesReply({})
  mount([apt('1'), apt('2', { id: 2, is_active: false })])
  // Подписи есть ровно один раз — в легенде над заголовками.
  expect(screen.getAllByText('Активен')).toHaveLength(1)
  expect(screen.getAllByText('Неактивен')).toHaveLength(1)
  expect(screen.getAllByRole('img', { name: 'Активен' })).toHaveLength(1)
  expect(screen.getAllByRole('img', { name: 'Неактивен' })).toHaveLength(1)
})

it('действия — иконки, у каждой есть доступное имя', async () => {
  balancesReply({})
  mount([apt('1'), apt('2', { id: 2, is_active: false })])
  expect(screen.getAllByRole('button', { name: 'Редактировать' })).toHaveLength(2)
  expect(screen.getByRole('button', { name: 'Деактивировать' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Активировать' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Удалить' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Удалить навсегда' })).toBeInTheDocument()
})

it('долг красный со знаком «−», предоплата зелёная с «+», подтверждённый ноль нейтральный', async () => {
  balancesReply({
    '1385000001': { debt: '545332.26', prepayment: '0.00', as_of: '2026-09-06', source: 'Accounting', filename: 'r.csv', import_id: 3, line: 2, currency: 'UZS' },
    '1385000002': { debt: '0.00', prepayment: '377.42', as_of: '2026-09-06', source: 'Accounting', filename: 'r.csv', import_id: 3, line: 3, currency: 'UZS' },
    '1385000003': { debt: '0.00', prepayment: '0.00', as_of: '2026-09-06', source: 'Accounting', filename: 'r.csv', import_id: 3, line: 4, currency: 'UZS' },
  })
  mount([apt('1'), apt('2', { id: 2 }), apt('3', { id: 3 })])
  const debt = await screen.findByText(/^−/)
  expect(debt).toHaveClass('text-red')
  expect(screen.getByText(/^\+/)).toHaveClass('text-emerald')
  const zero = screen.getByText(/^0[.,]00$/)
  expect(zero).toHaveClass('text-text-muted')
  expect(zero).not.toHaveClass('text-red')
})

it('квартира без лицевого счёта не запрашивает баланс и показывает прочерк', async () => {
  const post = balancesReply({})
  mount([apt('1', { account_number: null })])
  await waitFor(() => expect(post).not.toHaveBeenCalled())
  expect(screen.getAllByText('—').length).toBeGreaterThan(0)
})

it('недоступность сервиса показывается словом, а не нулём', async () => {
  vi.spyOn(apiClient, 'post').mockRejectedValue(new Error('Offline'))
  mount([apt('1')])
  expect(await screen.findByText('недоступно')).toBeInTheDocument()
  expect(screen.queryByText(/^0[.,]00$/)).not.toBeInTheDocument()
})

it('счёт без активной выгрузки — «нет данных», не ноль', async () => {
  balancesReply({})
  mount([apt('1')])
  expect(await screen.findByText('нет данных')).toBeInTheDocument()
  expect(screen.queryByText(/^0[.,]00$/)).not.toBeInTheDocument()
})

it('в легенде — самая свежая дата отчёта и метка расхождения', async () => {
  balancesReply({
    '1385000001': { debt: '10.00', prepayment: '0.00', as_of: '2026-09-06', source: 'Accounting', filename: 'new.csv', import_id: 4, line: 2, currency: 'UZS' },
    '1385000002': { debt: '20.00', prepayment: '0.00', as_of: '2026-08-01', source: 'Accounting', filename: 'old.csv', import_id: 2, line: 2, currency: 'UZS' },
  })
  mount([apt('1'), apt('2', { id: 2 })])
  const legend = await screen.findByText(/Данные на дату/)
  expect(legend.textContent).toContain('Accounting')
  // Сверяем каноническим форматтером, а не строкой: важно, что выбрана свежая
  // дата отчёта, а не августовская, — формат зависит от локали окружения.
  expect(legend.textContent).toContain(formatBusinessDate('2026-09-06'))
  expect(legend.textContent).not.toContain(formatBusinessDate('2026-08-01'))
  expect(screen.getByText('часть данных на другую дату')).toBeInTheDocument()
  expect(screen.getAllByLabelText('часть данных на другую дату')).toHaveLength(1)
})

it('при выключённом разделе платежей колонки баланса нет и запрос не уходит', async () => {
  vi.stubEnv('VITE_PAYMENTS_ENABLED', 'false')
  const post = balancesReply({})
  mount([apt('1')])
  await waitFor(() => expect(post).not.toHaveBeenCalled())
  expect(screen.queryByText('Баланс')).not.toBeInTheDocument()
  // Лицевой счёт — поле самой квартиры, оно видно и без платёжного сервиса.
  expect(screen.getByText('Лицевой счёт')).toBeInTheDocument()
  expect(screen.getByText('138500000 1'.replace(' ', ''))).toBeInTheDocument()
})

it('запрашивает счета одним пакетом, а не по одному на строку', async () => {
  const post = balancesReply({})
  mount([apt('2', { id: 2 }), apt('1')])
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
  expect(post.mock.calls[0][0]).toBe('/api/v2/payment-control/accounts/balances')
  expect(post.mock.calls[0][1]).toEqual({ account_numbers: ['1385000001', '1385000002'] })
})

it('колонка «Комнаты» убрана, подъезд и этаж сведены в одну графу', async () => {
  balancesReply({})
  mount([apt('1')])
  expect(screen.queryByText('Комнаты')).not.toBeInTheDocument()
  expect(screen.getByText('Подъезд / Этаж')).toBeInTheDocument()
  expect(screen.getByText('1 / 2')).toBeInTheDocument()
})

it('дворы и здания сохраняют подпись статуса', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AddressTable level="yards" yards={[{ id: 1, name: 'Двор', address: null, description: null, is_active: true, created_at: null, buildings_count: 1 }]} />
    </QueryClientProvider>,
  )
  const rows = screen.getByText('Двор').closest('div')!.parentElement!
  expect(within(rows).getAllByText('Активен').length).toBeGreaterThan(0)
})

// -- Сортировка -----------------------------------------------------------

/** Порядок номеров квартир — то, что реально видит пользователь. */
function numbers(): (string | null)[] {
  return screen.getAllByText(/^(1|2|10|100)$/).map(el => el.textContent)
}

it('клик по заголовку сортирует, второй переворачивает, третий возвращает исходный', async () => {
  balancesReply({})
  const user = userEvent.setup()
  mount([apt('100'), apt('10'), apt('2'), apt('1')])
  const header = () => screen.getByRole('button', { name: 'Номер квартиры' })

  expect(numbers()).toEqual(['1', '2', '10', '100'])
  await user.click(header())
  expect(numbers()).toEqual(['1', '2', '10', '100'])
  await user.click(header())
  expect(numbers()).toEqual(['100', '10', '2', '1'])
  await user.click(header())
  expect(numbers()).toEqual(['1', '2', '10', '100'])
})

it('состояние сортировки объявлено через aria-sort', async () => {
  balancesReply({})
  const user = userEvent.setup()
  mount([apt('2', { id: 2 }), apt('1')])
  const cell = () => screen.getByRole('columnheader', { name: /Номер квартиры/ })

  expect(cell()).toHaveAttribute('aria-sort', 'none')
  await user.click(screen.getByRole('button', { name: 'Номер квартиры' }))
  expect(cell()).toHaveAttribute('aria-sort', 'ascending')
  await user.click(screen.getByRole('button', { name: 'Номер квартиры' }))
  expect(cell()).toHaveAttribute('aria-sort', 'descending')
})

it('квартиры без площади остаются внизу в обе стороны', async () => {
  balancesReply({})
  const user = userEvent.setup()
  mount([apt('1', { area: 52 }), apt('2', { id: 2, area: null }), apt('10', { id: 10, area: 80 })])
  const header = () => screen.getByRole('button', { name: 'Площадь' })

  await user.click(header())
  expect(numbers()).toEqual(['1', '10', '2'])
  await user.click(header())
  expect(numbers()).toEqual(['10', '1', '2'])
})

it('крупнейший должник поднимается наверх, строка без снимка остаётся внизу', async () => {
  balancesReply({
    '1385000001': { debt: '1000.00', prepayment: '0.00', as_of: '2026-09-06', source: 'Accounting', currency: 'UZS' },
    '1385000002': { debt: '0.00', prepayment: '50.00', as_of: '2026-09-06', source: 'Accounting', currency: 'UZS' },
  })
  const user = userEvent.setup()
  mount([apt('2', { id: 2 }), apt('1'), apt('10', { id: 10 })])

  await user.click(await screen.findByRole('button', { name: 'Баланс' }))
  expect(numbers()).toEqual(['1', '2', '10'])
})

it('пока снимки балансов не доехали, заголовок «Баланс» не кликается', async () => {
  vi.spyOn(apiClient, 'post').mockReturnValue(new Promise(() => {}) as never)
  mount([apt('1')])
  expect(screen.getByText('Баланс')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Баланс' })).not.toBeInTheDocument()
})

it('колонка действий заголовком не сортируется', async () => {
  balancesReply({})
  mount([apt('1')])
  expect(screen.queryByRole('button', { name: 'Действия' })).not.toBeInTheDocument()
})

it('дома сортируются по числу квартир', async () => {
  const user = userEvent.setup()
  const building = (id: number, address: string, apartments_count: number): BuildingBrief => ({
    id, address, yard_id: 1, yard_name: null, entrance_count: 2, floor_count: 9,
    description: null, gps_latitude: null, gps_longitude: null, is_active: true,
    created_at: null, apartments_count,
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AddressTable
        level="buildings"
        buildings={[building(1, 'Yangi Olmazor, 1G', 104), building(2, 'Yangi Olmazor, 6G', 54)]}
      />
    </QueryClientProvider>,
  )

  const houses = () => screen.getAllByText(/^Yangi Olmazor/).map(el => el.textContent)
  // Счётчики начинают с убывания: «где квартир больше всего» — частый вопрос.
  await user.click(screen.getByRole('button', { name: 'Квартир' }))
  expect(houses()).toEqual(['Yangi Olmazor, 1G', 'Yangi Olmazor, 6G'])
  await user.click(screen.getByRole('button', { name: 'Квартир' }))
  expect(houses()).toEqual(['Yangi Olmazor, 6G', 'Yangi Olmazor, 1G'])
})
