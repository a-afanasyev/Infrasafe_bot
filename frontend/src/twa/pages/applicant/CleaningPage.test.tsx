import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../../test/test-utils'
import { server } from '../../../test/msw/server'
import CleaningCard from '../../../components/home/CleaningCard'
import type { PublicCleaningBuilding } from '../../../hooks/usePublicCleaning'
import ResidentCleaningPage from './CleaningPage'
import ResidentCleaningEntry from './ResidentCleaningEntry'

const BUILDING: PublicCleaningBuilding = {
  building_id: 1, address: 'д. 12', entrance_count: 2, work_date: '2026-11-17',
  entrances: [
    { entrance: 1, state: 'done', done_at: '2026-11-17T06:05:00Z', photo_ids: [31] },
    { entrance: 2, state: 'pending', done_at: null, photo_ids: [] },
  ],
  week: [[{ work_kind: 'wet', floor_from: 1, floor_to: 5 }], [{ work_kind: 'elevator' }], [{ work_kind: 'parking', entrances: [2] }], [], [], [], []],
}

beforeEach(() => {
  server.use(
    http.get('*/api/v2/profile/request-addresses', () => HttpResponse.json({
      yards: [], buildings: [], apartments: [{ id: 5, label: 'д. 12, кв. 5', building_id: 1 }] })),
    http.get('*/api/v2/public/cleaning/buildings/1', () => HttpResponse.json(BUILDING)),
  )
})

describe('ResidentCleaningPage', () => {
  it('показывает подъезды, график и принимает жалобу на свой дом', async () => {
    let body: unknown = null
    server.use(http.post('*/api/v2/cleaning/complaints', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ id: 9, request_number: '261117-004' }, { status: 201 })
    }))
    const user = userEvent.setup()
    render(<ResidentCleaningPage />)

    expect(await screen.findByText(/Убрано в/)).toBeInTheDocument()
    expect(screen.getByText('Ещё не убрано')).toBeInTheDocument()
    expect(screen.getByAltText('Фото уборки, подъезд 1')).toHaveAttribute('src', expect.stringContaining('/api/v2/public/cleaning/photos/31'))
    expect(screen.getByText('Влажная уборка 1–5')).toBeInTheDocument()
    expect(screen.getByText('Уборка выхода на парковку (под. 2)')).toBeInTheDocument()
    expect(screen.getAllByText('выходной')).toHaveLength(4)

    await user.click(screen.getAllByRole('button', { name: 'Сообщить: не убрано' })[1])
    await waitFor(() => expect(body).toEqual({ building_id: 1, entrance: 2 }))
    expect(await screen.findByText('Принято. Заявка 261117-004')).toBeInTheDocument()
  })

  it('честно говорит, если уборка дома жителям не публикуется', async () => {
    server.use(http.get('*/api/v2/public/cleaning/buildings/1', () => new HttpResponse(null, { status: 404 })))
    render(<ResidentCleaningPage />)
    expect(await screen.findByText('Сведения об уборке вашего дома пока не публикуются.')).toBeInTheDocument()
  })
})

describe('ResidentCleaningEntry', () => {
  it('на главной приложения показывает счёт подъездов; для скрытого дома пуста', async () => {
    const { unmount } = render(<ResidentCleaningEntry />)
    expect(await screen.findByTestId('resident-cleaning-entry')).toHaveTextContent('убрано подъездов: 1 из 2')
    unmount()
    server.use(http.get('*/api/v2/public/cleaning/buildings/1', () => new HttpResponse(null, { status: 404 })))
    const { container } = render(<ResidentCleaningEntry />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})

describe('CleaningCard', () => {
  it('считает дома, а не подъезды', async () => {
    server.use(http.get('*/api/v2/public/cleaning/today', () => HttpResponse.json({
      enabled: true, work_date: '2026-11-17', buildings_total: 2, buildings_done: 1,
      buildings: [
        { building_id: 1, address: 'д. 12', state: 'done' },
        { building_id: 2, address: 'д. 14', state: 'in_progress' },
        { building_id: 3, address: 'д. 16', state: 'none' },
      ],
    })))
    render(<CleaningCard title="" />)
    expect(await screen.findByText('домов убрано сегодня')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('убирают')).toBeInTheDocument()
    expect(screen.getByText('нет расписания')).toBeInTheDocument()
  })

  it('группирует дома по дворам, выносит общий адрес в заголовок и сортирует 10G после 9G', async () => {
    const house = (id: number, n: string, yard: number, state: string, done_at: string | null = null) => ({
      building_id: id, address: `Yangi Olmazor, ${n}`, state, done_at, yard_id: yard, yard_name: `Olmazor City Phase ${yard}` })
    server.use(http.get('*/api/v2/public/cleaning/today', () => HttpResponse.json({
      enabled: true, work_date: '2026-11-17', buildings_total: 4, buildings_done: 3,
      buildings: [
        house(3, '10G', 3, 'done', '2026-11-17T06:05:00Z'), house(4, '9G', 3, 'planned'),
        house(1, '14V', 1, 'done', '2026-11-17T05:40:00Z'), house(2, '15V', 1, 'done', '2026-11-17T08:00:00Z'),
      ],
    })))
    const { container } = render(<CleaningCard title="" />)
    expect(await screen.findByRole('heading', { name: 'Уборка домов · Yangi Olmazor' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Olmazor City Phase 1/ })).toHaveTextContent('убраны все: 2')
    expect(screen.getByRole('heading', { name: /Olmazor City Phase 3/ })).toHaveTextContent('1 из 2')
    expect([...container.querySelectorAll('.rh-cleaning-tile strong')].map((el) => el.textContent)).toEqual(['14V', '15V', '9G', '10G'])
  })

  it.each([false, true])('без единого дома для жителей блок не виден (модуль включён: %s)', async (enabled) => {
    let asked = false
    server.use(http.get('*/api/v2/public/cleaning/today', () => {
      asked = true
      return HttpResponse.json({ enabled, work_date: '2026-11-17', buildings_total: 0, buildings_done: 0, buildings: [] })
    }))
    const { container } = render(<CleaningCard title="Чистота" />)
    await waitFor(() => expect(asked).toBe(true))
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})
