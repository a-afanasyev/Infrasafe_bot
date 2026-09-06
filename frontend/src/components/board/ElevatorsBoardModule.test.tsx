import { describe, it, expect } from 'vitest'
import { render, screen } from '../../test/test-utils'
import ElevatorsBoardModule from './ElevatorsBoardModule'
import {
  EMPTY_PUBLIC_DATA,
  makePublicData,
  makePublicElevator,
  servePublicElevators,
} from '../../test/fixtures/publicElevators'

// T17 (Р17) — модуль табло стал СВОДКОЙ: «N из M работают», чипы со счётчиками,
// до 5 проблемных лифтов, ссылка «Все лифты →» на /elevators. Данные — через
// msw (не мок хука): проверяем и ?lang, и рендер из реального JSON.

function chips() {
  return screen.getAllByTestId('elevator-status-chip').map((c) => [c.getAttribute('data-status'), c.textContent?.replace(/\s+/g, ' ').trim()])
}

describe('ElevatorsBoardModule (сводка)', () => {
  it('крупная строка «N из M работают», чипы только ненулевые (Работают — всегда), телефон диспетчерской', async () => {
    const seen = { value: null as string | null }
    servePublicElevators(
      makePublicData([
        makePublicElevator(),
        makePublicElevator({ elevator_number: 2, status: 'under_repair', status_since: '2026-09-01T09:00:00Z', label: 'ул. Мира, д. 5, подъезд 1, лифт 2' }),
        makePublicElevator({ entrance_number: 2, status: 'not_working', label: 'ул. Мира, д. 5, подъезд 2, лифт 1' }),
      ]),
      seen,
    )
    render(<ElevatorsBoardModule />)

    expect(await screen.findByText('1 из 3 работает')).toBeInTheDocument()
    expect(chips()).toEqual([
      ['working', 'Работают 1'],
      ['not_working', 'Не работают 1'],
      ['under_repair', 'В ремонте 1'],
    ])
    expect(screen.getByText(/Диспетчерская: \+998 71 123-45-67/)).toBeInTheDocument()
    expect(screen.getByText('Лифты')).toBeInTheDocument() // board.sections.elevators
    expect(seen.value).toBe('ru')
  })

  it('чип «Работают» показывается даже при нуле; нулевые остальные скрыты', async () => {
    servePublicElevators(makePublicData([makePublicElevator({ status: 'not_working' })]))
    render(<ElevatorsBoardModule />)
    expect(await screen.findByText('0 из 1 работает')).toBeInTheDocument()
    expect(chips()).toEqual([
      ['working', 'Работают 0'],
      ['not_working', 'Не работают 1'],
    ])
  })

  it('проблемные лифты (not_working/under_repair) — короткие строки «подпись — статус с DD.MM», без рабочих', async () => {
    servePublicElevators(
      makePublicData([
        makePublicElevator(),
        makePublicElevator({ elevator_number: 2, status: 'under_repair', status_since: '2026-09-01T09:00:00Z', label: 'ул. Мира, д. 5, подъезд 1, лифт 2' }),
        makePublicElevator({ entrance_number: 2, status: 'not_working', status_since: null, label: 'ул. Мира, д. 5, подъезд 2, лифт 1' }),
        makePublicElevator({ entrance_number: 3, status: 'maintenance', label: 'ул. Мира, д. 5, подъезд 3, лифт 1' }),
      ]),
    )
    render(<ElevatorsBoardModule />)

    const rows = await screen.findAllByTestId('elevator-problem-row')
    expect(rows.map((r) => r.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
      'ул. Мира, д. 5, подъезд 1, лифт 2 В ремонте с 01.09',
      'ул. Мира, д. 5, подъезд 2, лифт 1 Не работает',
    ])
    expect(screen.queryByText(/и ещё/)).not.toBeInTheDocument()
    expect(screen.queryByText('Все лифты работают')).not.toBeInTheDocument()
  })

  it('больше 5 проблемных → ровно 5 строк и «и ещё K»', async () => {
    const problems = Array.from({ length: 7 }, (_, i) =>
      makePublicElevator({ entrance_number: i + 1, status: i % 2 ? 'not_working' : 'under_repair', label: `лифт-${i + 1}` }),
    )
    servePublicElevators(makePublicData([makePublicElevator({ entrance_number: 9 }), ...problems]))
    render(<ElevatorsBoardModule />)

    expect(await screen.findByText('1 из 8 работает')).toBeInTheDocument()
    expect(screen.getAllByTestId('elevator-problem-row')).toHaveLength(5)
    expect(screen.getByText('лифт-5')).toBeInTheDocument()
    expect(screen.queryByText('лифт-6')).not.toBeInTheDocument()
    expect(screen.getByText('и ещё 2')).toBeInTheDocument()
  })

  it('без проблемных → «Все лифты работают»; ссылка «Все лифты →» ведёт на /elevators', async () => {
    servePublicElevators(makePublicData([makePublicElevator(), makePublicElevator({ elevator_number: 2 })]))
    render(<ElevatorsBoardModule />)

    expect(await screen.findByText('2 из 2 работают')).toBeInTheDocument()
    expect(screen.getByText('Все лифты работают')).toBeInTheDocument()
    expect(screen.queryByTestId('elevator-problem-row')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Все лифты →' })).toHaveAttribute('href', '/elevators')
  })

  it('старый ответ API без summary → сводка досчитывается по yards', async () => {
    servePublicElevators({ ...makePublicData([makePublicElevator(), makePublicElevator({ elevator_number: 2, status: 'maintenance' })]), summary: undefined })
    render(<ElevatorsBoardModule />)
    expect(await screen.findByText('1 из 2 работает')).toBeInTheDocument()
    expect(chips()).toEqual([
      ['working', 'Работают 1'],
      ['maintenance', 'На ТО 1'],
    ])
  })

  it('пустой ответ → модуль НЕ пропадает: заглушка, без телефона, чипов и ссылки', async () => {
    servePublicElevators(EMPTY_PUBLIC_DATA)
    render(<ElevatorsBoardModule title="Наши лифты" />)

    expect(await screen.findByText('Данные о лифтах пока не опубликованы')).toBeInTheDocument()
    expect(screen.getByText('Наши лифты')).toBeInTheDocument()
    expect(screen.queryByText(/Диспетчерская/)).not.toBeInTheDocument()
    expect(screen.queryByTestId('elevator-status-chip')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Все лифты →' })).not.toBeInTheDocument()
  })
})
