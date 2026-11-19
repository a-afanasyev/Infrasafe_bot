import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, within } from '../test/test-utils'
import { server } from '../test/msw/server'
import ResidentCleaningPage from './ResidentCleaningPage'
import CleaningCard from '../components/home/CleaningCard'

const TODAY = {
  enabled: true, work_date: '2026-11-17', buildings_total: 2, buildings_done: 1,
  buildings: [
    {
      building_id: 1, address: 'д. 12', state: 'done', done_at: '2026-11-17T06:05:00Z',
      entrances: [
        { entrance: 1, state: 'done', done_at: '2026-11-17T04:40:00Z', photo_ids: [31, 32] },
        { entrance: 2, state: 'done', done_at: '2026-11-17T06:05:00Z', photo_ids: [] },
      ],
    },
    {
      building_id: 2, address: 'д. 14', state: 'in_progress', done_at: null,
      entrances: [{ entrance: 1, state: 'pending', done_at: null, photo_ids: [] }],
    },
    { building_id: 3, address: 'д. 16', state: 'none', done_at: null, entrances: [{ entrance: 1, state: 'none', done_at: null, photo_ids: [] }] },
  ],
}

const serve = (body: unknown) => server.use(http.get('*/api/v2/public/cleaning/today', () => HttpResponse.json(body)))

describe('ResidentCleaningPage', () => {
  it('показывает все дома со статусами подъездов и миниатюрами; миниатюра открывает фото', async () => {
    serve(TODAY)
    const user = userEvent.setup()
    render(<ResidentCleaningPage />)

    const first = (await screen.findByRole('heading', { name: 'д. 12' })).closest('article') as HTMLElement
    expect(within(first).getByText('Убрано · 11:05')).toBeInTheDocument()        // время — в зоне площадки
    expect(within(first).getByText('Убрано в 09:40')).toBeInTheDocument()
    // подъезд — одна строка; фото появляются только после «Подробнее»
    expect(within(first).getAllByRole('button')).toHaveLength(1)
    expect(within(first).queryByRole('img', { hidden: true })).toBeNull()
    await user.click(within(first).getByRole('button', { name: 'Подробнее · 2 фото' }))
    expect(within(first).getAllByRole('button', { name: /Фото уборки/ })).toHaveLength(2)
    expect(within(first).getByRole('button', { name: 'Свернуть' })).toHaveAttribute('aria-expanded', 'true')

    const second = screen.getByRole('heading', { name: 'д. 14' }).closest('article') as HTMLElement
    expect(within(second).getByText('Идёт уборка')).toBeInTheDocument()
    expect(within(second).getByText('Ещё не убрано')).toBeInTheDocument()
    expect(within(second).queryByRole('button')).toBeNull()                       // не принято — фото нет
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1')
    expect(screen.getByRole('link', { name: 'Сообщить в боте' })).toHaveAttribute('href', expect.stringContaining('https://t.me/'))

    await user.click(screen.getByRole('button', { name: 'Фото уборки: д. 12, подъезд 1, кадр 2' }))
    const viewer = screen.getByRole('dialog')
    // миниатюра — превью, в просмотре — оригинал
    expect(within(viewer).getByRole('img')).toHaveAttribute('src', expect.stringContaining('/api/v2/public/cleaning/photos/32?original=true'))
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('без домов для жителей — пояснение, а не пустая сетка', async () => {
    serve({ enabled: true, work_date: '2026-11-17', buildings_total: 0, buildings_done: 0, buildings: [] })
    render(<ResidentCleaningPage />)
    expect(await screen.findByText('Сведения об уборке домов пока не публикуются.')).toBeInTheDocument()
  })
})

describe('CleaningCard: сводка на главной', () => {
  it('показывает время «убрано», полосу хода и ссылку на обзор', async () => {
    serve(TODAY)
    render(<CleaningCard title="" />)
    expect(await screen.findByText('✓ 11:05')).toBeInTheDocument()            // плитка дома: время вместо «Убрано · …»
    expect(screen.getByTitle('д. 12 — Убрано · 11:05')).toBeInTheDocument()   // полная подпись — в подсказке
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuemax', '2')
    expect(screen.getByRole('link', { name: /Все дома и фото/ })).toHaveAttribute('href', expect.stringContaining('/cleaning'))
  })
})
