import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '../../../test/test-utils'
import DispatchPage from './DispatchPage'

// Экран диспетчера: телефон → адрес из справочника → что случилось → сводка.
// ИИ только проверяет перед отправкой; замечание — совет, а не запрет.

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))
vi.mock('../../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost } }))

const CC = '/api/v2/callcenter'
type Issue = { field: string; code: string; suggestion: string | null; options: unknown[] }

let aiOn = false
let residents: unknown[] = []
let checks: Array<{ issues: Issue[] } | Error> = []

function mockApi() {
  mockGet.mockImplementation((url: string) => {
    if (url === `${CC}/capabilities`) return Promise.resolve({ data: { address_suggest: aiOn } })
    if (url === `${CC}/search-resident`) return Promise.resolve({ data: residents })
    if (url === `${CC}/residents/7/apartments`)
      return Promise.resolve({ data: [{ id: 12, label: 'Yangi Olmazor, 4G, кв. 12', building_id: 4 }] })
    if (url === '/api/v2/addresses/yards') return Promise.resolve({ data: [{ id: 1, name: 'Olmazor City' }] })
    if (url === '/api/v2/addresses/yards/1/buildings')
      return Promise.resolve({ data: [{ id: 4, address: 'Yangi Olmazor, 4G' }] })
    if (url === `${CC}/buildings/4/apartments`)
      return Promise.resolve({ data: [{ id: 70, number: '7' }, { id: 12, number: '12' }] })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
  mockPost.mockImplementation((url: string) => {
    if (url === `${CC}/check`) {
      const next = checks.shift()
      if (!next || next instanceof Error) return Promise.reject(next ?? new Error('no check queued'))
      return Promise.resolve({ data: { ai_used: true, ...next } })
    }
    if (url === `${CC}/requests`) return Promise.resolve({ data: { request_number: '261111-007' } })
    return Promise.reject(new Error(`unexpected POST ${url}`))
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  sessionStorage.clear()
  aiOn = false
  residents = []
  checks = []
  mockApi()
})

const created = () => mockPost.mock.calls.filter(([url]) => url === `${CC}/requests`).map(([, body]) => body)
const checked = () => mockPost.mock.calls.filter(([url]) => url === `${CC}/check`)

type User = ReturnType<typeof userEvent.setup>

async function enterPhone(user: User) {
  await user.type(screen.getByRole('textbox', { name: 'Телефон звонящего' }), '+998 90 111-22-33')
  await user.click(screen.getByRole('button', { name: 'Далее' }))
}

async function describeProblem(user: User, category = 'Сантехника') {
  await user.click(await screen.findByRole('button', { name: category }))
  await user.type(screen.getByRole('textbox', { name: 'Опишите проблему' }), 'течёт труба в подвале')
  await user.click(screen.getByRole('button', { name: 'Далее' }))
  await user.click(screen.getByRole('button', { name: 'Средняя' }))
  expect(await screen.findByText('Проверьте заявку')).toBeInTheDocument()
}

/** Незнакомый номер → двор → дом → «Весь дом» → проблема → сводка. */
async function walkStranger(user: User, category?: string) {
  await enterPhone(user)
  await user.type(await screen.findByRole('textbox', { name: 'Как зовут звонящего?' }), 'Азиз')
  await user.click(screen.getByRole('button', { name: 'Далее' }))
  await user.click(await screen.findByRole('button', { name: 'Olmazor City' }))
  await user.click(await screen.findByRole('button', { name: 'Yangi Olmazor, 4G' }))
  await user.click(await screen.findByRole('button', { name: /Весь дом/ }))
  await describeProblem(user, category)
}

describe('DispatchPage — приём звонка', () => {
  it('незнакомый номер: адрес из справочника, звонящий в примечаниях, приёмка у менеджера', async () => {
    const user = userEvent.setup()
    render(<DispatchPage />)
    await walkStranger(user)
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    expect(await screen.findByText('Заявка 261111-007 принята')).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith(`${CC}/search-resident`, { params: { q: '901112233' } })
    expect(created()).toEqual([{
      category: 'plumbing', urgency: 'medium', description: 'течёт труба в подвале', building_id: 4,
      caller_name: 'Азиз', caller_phone: '+998901112233', acceptance_mode: 'manager',
    }])
    expect(checked()).toHaveLength(0) // ИИ на площадке выключен — заявка уходит сразу

    await user.click(screen.getByRole('button', { name: 'Новая заявка' }))
    expect(screen.getByRole('textbox', { name: 'Телефон звонящего' })).toHaveValue('')
  })

  it('житель найден по телефону: его квартира в одно касание, заявка от его имени', async () => {
    residents = [{ id: 7, full_name: 'Resident User', phone: '+998901112233' }]
    const user = userEvent.setup()
    render(<DispatchPage />)
    await enterPhone(user)
    await user.click(await screen.findByRole('button', { name: 'Resident User' }))
    await user.click(await screen.findByRole('button', { name: 'Yangi Olmazor, 4G, кв. 12' }))
    await describeProblem(user)
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await screen.findByText('Заявка 261111-007 принята')
    expect(created()).toEqual([{
      category: 'plumbing', urgency: 'medium', description: 'течёт труба в подвале', apartment_id: 12, user_id: 7,
    }])
  })

  it('квартира из каскада: двор → дом → номер', async () => {
    const user = userEvent.setup()
    render(<DispatchPage />)
    await enterPhone(user)
    await user.click(await screen.findByRole('button', { name: 'Далее' })) // имя не знаем
    await user.click(await screen.findByRole('button', { name: 'Olmazor City' }))
    await user.click(await screen.findByRole('button', { name: 'Yangi Olmazor, 4G' }))
    await user.click(await screen.findByRole('button', { name: 'кв. 7' }))
    await describeProblem(user)
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await screen.findByText('Заявка 261111-007 принята')
    expect(created()[0]).toMatchObject({ apartment_id: 70, caller_phone: '+998901112233' })
    expect(created()[0]).not.toHaveProperty('caller_name')
  })
})

describe('DispatchPage — проверка ИИ', () => {
  const MISMATCH: Issue = { field: 'category', code: 'category_mismatch', suggestion: 'plumbing', options: [] }

  it('замечание останавливает отправку; «Исправить» подставляет и отправляет без повторной проверки', async () => {
    aiOn = true
    checks = [{ issues: [MISMATCH] }]
    const user = userEvent.setup()
    render(<DispatchPage />)
    await walkStranger(user, 'Электрика')
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    expect(await screen.findByText('По описанию это больше похоже на «Сантехника».')).toBeInTheDocument()
    expect(created()).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Исправить' }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await screen.findByText('Заявка 261111-007 принята')
    expect(created()[0]).toMatchObject({ category: 'plumbing' })
    expect(checked()).toHaveLength(1)
  })

  it('«Оставить так»: заявка уходит как есть', async () => {
    aiOn = true
    checks = [{ issues: [MISMATCH] }]
    const user = userEvent.setup()
    render(<DispatchPage />)
    await walkStranger(user, 'Электрика')
    await user.click(screen.getByRole('button', { name: 'Отправить' }))
    await user.click(await screen.findByRole('button', { name: 'Оставить так' }))
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await screen.findByText('Заявка 261111-007 принята')
    expect(created()[0]).toMatchObject({ category: 'electricity' })
    expect(checked()).toHaveLength(1)
  })

  it('адрес: вариант из справочника подставляется одним касанием', async () => {
    aiOn = true
    const option = { type: 'building', id: 14, yard_id: 1, label: 'Yangi Olmazor, 14G (Olmazor City)' }
    checks = [{ issues: [{ field: 'address', code: 'address_mismatch', suggestion: null, options: [option] }] }]
    const user = userEvent.setup()
    render(<DispatchPage />)
    await walkStranger(user)
    await user.click(screen.getByRole('button', { name: 'Отправить' }))
    await user.click(await screen.findByRole('button', { name: option.label }))
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await screen.findByText('Заявка 261111-007 принята')
    expect(created()[0]).toMatchObject({ building_id: 14 })
  })

  it('сбой проверки не мешает принять звонок', async () => {
    aiOn = true
    checks = [new Error('model down')]
    const user = userEvent.setup()
    render(<DispatchPage />)
    await walkStranger(user)
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await screen.findByText('Заявка 261111-007 принята')
    expect(created()).toHaveLength(1)
  })
})
