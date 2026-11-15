import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../test/test-utils'
import OutageEntry from './OutageEntry'
import OutagePage from './OutagePage'

// Отключения от сантехника: кнопка на экране смены и мастер «что → дома → на сколько».

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))
vi.mock('../twaClient', () => ({ twaClient: { get: mockGet, post: mockPost, patch: vi.fn() } }))

const BASE = '/api/v2/board-config/notices/outages'
const YARDS = [{ id: 1, name: 'Двор Северный', buildings: [{ id: 12, address: 'Садовая, 12' }, { id: 14, address: 'Садовая, 14' }] }]
const OPEN = { id: 5, resource: 'water', title_ru: 'Отключена вода — Садовая, 14', title_uz: '' }
let options: object

beforeEach(() => {
  options = { allowed: true, reason: null, yards: YARDS, open: [] }
  mockGet.mockReset()
  mockPost.mockReset()
  mockGet.mockImplementation((url: string) => (url === `${BASE}/options` ? Promise.resolve({ data: options }) : Promise.reject(new Error(url))))
  mockPost.mockResolvedValue({ data: OPEN })
})

describe('OutageEntry', () => {
  it('сантехнику на смене — «Отключил воду»; незакрытое — «Воду включили» → «Да» → POST close', async () => {
    options = { allowed: true, reason: null, yards: YARDS, open: [OPEN] }
    render(<OutageEntry to="/twa/s/outage" />)
    expect(await screen.findByRole('button', { name: /Отключил воду/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Воду включили/ }))
    expect(screen.getByRole('dialog', { name: 'Уже включили?' })).toHaveTextContent('Садовая, 14')
    fireEvent.click(screen.getByRole('button', { name: /Да/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(`${BASE}/5/close`))
    expect(await screen.findByRole('status')).toHaveTextContent('Жителям сообщили')
  })

  it('сантехник вне смены: кнопка видна, но неактивна, с подсказкой; своё незакрытое закрыть можно', async () => {
    options = { allowed: false, reason: 'no_active_shift', yards: [], open: [OPEN] }
    const { unmount } = render(<OutageEntry to="/twa/s/outage" />)
    expect(await screen.findByRole('button', { name: /Воду включили/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: /Отключил воду/ })).toBeDisabled()
    expect(screen.getByText('Сначала начните смену')).toBeInTheDocument()
    unmount()

    // не сантехник: кнопки нет вовсе

    options = { allowed: false, reason: 'not_plumber', yards: [], open: [] }
    render(<OutageEntry to="/twa/s/outage" />)
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
    expect(screen.queryByTestId('outage-entry')).not.toBeInTheDocument()
  })
})

describe('OutagePage', () => {
  it('что → дома → на сколько → «Да»: один POST с выбранным', async () => {
    render(<OutagePage backTo="/twa/s/shift" />)
    fireEvent.click(await screen.findByRole('button', { name: /Вода/ }))
    expect(screen.getByRole('button', { name: /Далее/ })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Садовая, 12' }))
    fireEvent.click(screen.getByRole('button', { name: 'Садовая, 14' }))
    fireEvent.click(screen.getByRole('button', { name: 'Садовая, 12' })) // передумал
    fireEvent.click(screen.getByRole('button', { name: /Далее/ }))
    fireEvent.click(screen.getByRole('button', { name: '2 часа' }))
    expect(screen.getByRole('dialog', { name: 'Сообщить жителям?' })).toHaveTextContent('Садовая, 14')
    expect(mockPost).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Да/ }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(BASE, { resource: 'water', building_ids: [14], duration: '2h' }))
  })

  it('отказ сервера показан понятной фразой; не на смене — мастер не открывается', async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: 'already_open' } } })
    const { unmount } = render(<OutagePage backTo="/twa/s/shift" />)
    fireEvent.click(await screen.findByRole('button', { name: /Отопление/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Садовая, 12' }))
    fireEvent.click(screen.getByRole('button', { name: /Далее/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Не знаю' }))
    fireEvent.click(screen.getByRole('button', { name: /Да/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('По этому дому уже объявлено')
    unmount()

    options = { allowed: false, reason: 'no_active_shift', yards: [], open: [] }
    render(<OutagePage backTo="/twa/s/shift" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Сначала начните смену')
  })
})
