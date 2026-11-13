import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../test/test-utils'
import { server } from '../test/msw/server'
import DispatcherPage from './DispatcherPage'

// Веб-страница диспетчера: вся заявка по звонку на одном экране.

type Body = Record<string, unknown>

function mockDirectories(ai = false) {
  server.use(
    http.get('*/api/v2/callcenter/capabilities', () => HttpResponse.json({ address_suggest: ai })),
    http.get('*/api/v2/addresses/yards', () => HttpResponse.json([{ id: 3, name: 'Двор 3' }])),
    http.get('*/api/v2/addresses/yards/3/buildings', () => HttpResponse.json([{ id: 12, address: 'ул. Садовая, 14' }])),
    http.get('*/api/v2/callcenter/buildings/12/apartments', () => HttpResponse.json([{ id: 77, number: '15' }])),
    http.get('*/api/v2/callcenter/search-resident', () => HttpResponse.json([])),
  )
}

function captureCreate(): { body: () => Body | null } {
  let body: Body | null = null
  server.use(
    http.post('*/api/v2/callcenter/requests', async ({ request }) => {
      body = (await request.json()) as Body
      return HttpResponse.json({ request_number: '261113-007' }, { status: 201 })
    }),
  )
  return { body: () => body }
}

type User = ReturnType<typeof userEvent.setup>

async function fillStranger(user: User) {
  await user.type(screen.getByLabelText('Телефон звонящего *'), '90 555 00 11')
  await user.type(screen.getByLabelText('Как зовут звонящего?'), 'Рустам')
  await screen.findByRole('option', { name: 'Двор 3' })
  await user.selectOptions(screen.getByLabelText('Двор *'), '3')
  await screen.findByRole('option', { name: 'ул. Садовая, 14' })
  await user.selectOptions(screen.getByLabelText('Дом'), '12')
  await screen.findByRole('option', { name: '15' })
  await user.selectOptions(screen.getByLabelText('Квартира'), '77')
  await user.click(screen.getByRole('button', { name: 'Электрика' }))
  await user.type(screen.getByLabelText('Опишите проблему *'), 'Течёт труба')
}

describe('DispatcherPage', () => {
  it('незнакомый номер: заявка на квартиру из списков, звонящий в теле, приёмка у менеджера', async () => {
    mockDirectories()
    const created = captureCreate()
    const user = userEvent.setup()
    render(<DispatcherPage />)

    expect(screen.getByRole('button', { name: 'Отправить' })).toBeDisabled()
    await fillStranger(user)
    expect(screen.getByText('ул. Садовая, 14, кв. 15')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    expect(await screen.findByText('Заявка 261113-007 принята')).toBeInTheDocument()
    expect(created.body()).toEqual({
      category: 'electricity',
      urgency: 'low',
      description: 'Течёт труба',
      apartment_id: 77,
      caller_name: 'Рустам',
      caller_phone: '905550011',
      acceptance_mode: 'manager',
    })
    // форма очищена для следующего звонка
    expect(screen.getByLabelText('Телефон звонящего *')).toHaveValue('')
  })

  it('найденный житель: его квартира в одно нажатие, заявка от его имени', async () => {
    mockDirectories()
    server.use(
      http.get('*/api/v2/callcenter/search-resident', () =>
        HttpResponse.json([{ id: 5, full_name: 'Дилноза Рахимова', phone: '+998900000001' }])),
      http.get('*/api/v2/callcenter/residents/5/apartments', () =>
        HttpResponse.json([{ id: 77, label: 'ул. Садовая, 14, кв. 15', building_id: 12 }])),
    )
    const created = captureCreate()
    const user = userEvent.setup()
    render(<DispatcherPage />)

    await user.type(screen.getByLabelText('Телефон звонящего *'), '900000001')
    await user.click(await screen.findByRole('button', { name: 'Дилноза Рахимова' }))
    await user.click(await screen.findByRole('button', { name: 'ул. Садовая, 14, кв. 15' }))
    await user.click(screen.getByRole('button', { name: 'Сантехника' }))
    await user.type(screen.getByLabelText('Опишите проблему *'), 'Течёт кран')
    await user.click(screen.getByRole('button', { name: 'Отправить' }))

    await screen.findByText('Заявка 261113-007 принята')
    expect(created.body()).toEqual({
      category: 'plumbing', urgency: 'low', description: 'Течёт кран', apartment_id: 77, user_id: 5,
    })
  })

  it('переключатель языка в шапке переводит страницу на узбекский', async () => {
    mockDirectories()
    const user = userEvent.setup()
    render(<DispatcherPage />)

    await user.click(screen.getByRole('button', { name: "O'zb" }))
    expect(await screen.findByRole('heading', { name: "Qo'ng'iroq bo'yicha ariza" })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Yuborish' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Rus' }))
    expect(await screen.findByRole('heading', { name: 'Заявка по звонку' })).toBeInTheDocument()
  })

  it('замечание ИИ: «Исправить» подставляет категорию, повторная отправка создаёт заявку', async () => {
    mockDirectories(true)
    let checks = 0
    server.use(
      http.post('*/api/v2/callcenter/check', () => {
        checks += 1
        return HttpResponse.json({
          ai_used: true,
          issues: [{ field: 'category', code: 'category_mismatch', suggestion: 'plumbing', options: [] }],
        })
      }),
    )
    const created = captureCreate()
    const user = userEvent.setup()
    render(<DispatcherPage />)

    await fillStranger(user)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Отправить' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Отправить' }))
    expect(await screen.findByText('По описанию это больше похоже на «Сантехника».')).toBeInTheDocument()
    expect(created.body()).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Исправить' }))
    await user.click(screen.getByRole('button', { name: 'Отправить' }))
    await screen.findByText('Заявка 261113-007 принята')
    expect(created.body()).toMatchObject({ category: 'plumbing' })
    expect(checks).toBe(1)
  })
})
