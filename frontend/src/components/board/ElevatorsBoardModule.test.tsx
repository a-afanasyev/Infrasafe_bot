import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import ElevatorsBoardModule from './ElevatorsBoardModule'
import type { PublicElevator, PublicElevatorsData } from '../../hooks/usePublicElevators'

// T16 — модуль читает GET /api/v2/public/elevators через msw (не мок хука):
// проверяем и ?lang, и рендер групп из реального JSON-ответа.

function makeElevator(over: Partial<PublicElevator> = {}): PublicElevator {
  return {
    entrance_number: 1,
    elevator_number: 1,
    label: 'ул. Мира, д. 5, подъезд 1, лифт 1',
    status: 'working',
    status_since: '2026-09-03T12:00:00Z',
    availability_30d: 0.98,
    last_maintenance_on: '2026-08-01',
    cert_valid_until: '2027-01-15',
    cert_expired: false,
    service_org_name: 'ЛифтСервис',
    service_org_phone: '+998 71 000-00-00',
    manufacturer: 'OTIS',
    model: 'Gen2',
    production_year: 2015,
    capacity_kg: 630,
    downtime_reason: null,
    spare_part_expected_on: null,
    ...over,
  }
}

function makeData(elevators: PublicElevator[], over: Partial<PublicElevatorsData> = {}): PublicElevatorsData {
  return {
    yards: [
      {
        id: 1,
        name: 'Двор 1',
        buildings: [{ id: 1, address: 'ул. Мира, д. 5', elevators }],
      },
    ],
    dispatch_phone: '+998 71 123-45-67',
    generated_at: '2026-09-06T10:00:00Z',
    ...over,
  }
}

function serve(data: PublicElevatorsData, seenLang: { value: string | null } = { value: null }) {
  server.use(
    http.get('*/api/v2/public/elevators', ({ request }) => {
      seenLang.value = new URL(request.url).searchParams.get('lang')
      return HttpResponse.json(data)
    }),
  )
}

describe('ElevatorsBoardModule', () => {
  it('рендерит дом → подъезды → лифты со статус-пилюлями, «с {дата}» и телефоном диспетчера', async () => {
    const seen = { value: null as string | null }
    serve(
      makeData([
        makeElevator(),
        makeElevator({ elevator_number: 2, status: 'under_repair', status_since: '2026-09-01T09:00:00Z' }),
        makeElevator({ entrance_number: 2, status: 'not_working' }),
      ]),
      seen,
    )
    render(<ElevatorsBoardModule />)

    expect(await screen.findByText('ул. Мира, д. 5')).toBeInTheDocument()
    expect(screen.getByText('Подъезд 1')).toBeInTheDocument()
    expect(screen.getByText('Подъезд 2')).toBeInTheDocument()
    expect(screen.getAllByText('Лифт 1')).toHaveLength(2)
    expect(screen.getByText('Лифт 2')).toBeInTheDocument()

    const pills = screen.getAllByTestId('elevator-status-pill')
    expect(pills.map((p) => p.getAttribute('data-status'))).toEqual(['working', 'under_repair', 'not_working'])
    expect(screen.getByText('В ремонте')).toBeInTheDocument()
    expect(screen.getByText('Не работает')).toBeInTheDocument()
    expect(screen.getByText('с 01.09.2026')).toBeInTheDocument()

    expect(screen.getByText(/Диспетчерская: \+998 71 123-45-67/)).toBeInTheDocument()
    expect(screen.getByText('Лифты')).toBeInTheDocument() // board.sections.elevators
    expect(seen.value).toBe('ru')
  })

  it('пустой ответ → модуль НЕ пропадает, показывает заглушку без телефона', async () => {
    serve({ yards: [], dispatch_phone: null, generated_at: '2026-09-06T10:00:00Z' })
    render(<ElevatorsBoardModule title="Наши лифты" />)

    expect(await screen.findByText('Данные о лифтах пока не опубликованы')).toBeInTheDocument()
    expect(screen.getByText('Наши лифты')).toBeInTheDocument()
    expect(screen.queryByText(/Диспетчерская/)).not.toBeInTheDocument()
  })

  it('детали простоя показаны только когда пришли; строка обслуживания — только заполненное', async () => {
    serve(
      makeData([
        makeElevator({ status: 'under_repair', downtime_reason: 'Ждём лебёдку', spare_part_expected_on: '2026-09-20' }),
        makeElevator({
          elevator_number: 2, status: 'not_working', downtime_reason: null, spare_part_expected_on: null,
          service_org_name: null, service_org_phone: null, last_maintenance_on: null,
          cert_valid_until: '2020-01-01', cert_expired: true, availability_30d: null,
        }),
      ]),
    )
    render(<ElevatorsBoardModule />)

    expect(await screen.findByText('Причина: Ждём лебёдку · Запчасть ожидается 20.09.2026')).toBeInTheDocument()
    // availability_30d=0.98 → «доступность 98 %»; у второго лифта availability null → части нет.
    expect(screen.getByText('Обслуживает: ЛифтСервис · +998 71 000-00-00 · ТО 01.08.2026 · освид. до 15.01.2027 · доступность 98 %')).toBeInTheDocument()
    expect(screen.getByText('освид. до 01.01.2020 · освидетельствование просрочено')).toBeInTheDocument()
    expect(screen.getAllByText(/доступность/)).toHaveLength(1)
    expect(screen.getAllByText(/Причина:/)).toHaveLength(1)
  })

  it('имя двора показывается только при нескольких дворах', async () => {
    const one = makeData([makeElevator()])
    serve({
      ...one,
      yards: [
        ...one.yards,
        { id: 2, name: 'Двор 2', buildings: [{ id: 2, address: 'ул. Садовая, д. 1', elevators: [makeElevator()] }] },
      ],
    })
    render(<ElevatorsBoardModule />)
    expect(await screen.findByText('Двор 1')).toBeInTheDocument()
    expect(screen.getByText('Двор 2')).toBeInTheDocument()
  })
})
