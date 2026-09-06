import { http, HttpResponse } from 'msw'
import { server } from '../msw/server'
import type {
  PublicElevator,
  PublicElevatorYard,
  PublicElevatorsData,
  PublicElevatorsSummary,
} from '../../hooks/usePublicElevators'

/** Фикстуры публичного ответа GET /api/v2/public/elevators (табло T16 + страница T17). */

export function makePublicElevator(over: Partial<PublicElevator> = {}): PublicElevator {
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

/** Сводка, как её считает бэкенд — по всем лифтам ответа. */
export function summaryOfYards(yards: PublicElevatorYard[]): PublicElevatorsSummary {
  const all = yards.flatMap((y) => y.buildings.flatMap((b) => b.elevators))
  const count = (status: PublicElevator['status']) => all.filter((e) => e.status === status).length
  return {
    total: all.length,
    working: count('working'),
    not_working: count('not_working'),
    under_repair: count('under_repair'),
    maintenance: count('maintenance'),
  }
}

/** Один двор «Двор 1» с одним домом «ул. Мира, д. 5» и переданными лифтами. */
export function makePublicData(elevators: PublicElevator[], over: Partial<PublicElevatorsData> = {}): PublicElevatorsData {
  const yards = over.yards ?? [
    { id: 1, name: 'Двор 1', buildings: [{ id: 1, address: 'ул. Мира, д. 5', elevators }] },
  ]
  return {
    yards,
    summary: summaryOfYards(yards),
    dispatch_phone: '+998 71 123-45-67',
    generated_at: '2026-09-06T10:00:00Z',
    ...over,
  }
}

export const EMPTY_PUBLIC_DATA: PublicElevatorsData = {
  yards: [],
  summary: { total: 0, working: 0, not_working: 0, under_repair: 0, maintenance: 0 },
  dispatch_phone: null,
  generated_at: '2026-09-06T10:00:00Z',
}

/** Два двора: «Двор 1» (д. 5: 1 работает, 1 в ремонте; д. 3: 1 не работает) и «Двор 2» (Садовая: 1 на ТО, 1 работает). */
export function makeTwoYardsData(): PublicElevatorsData {
  const yards: PublicElevatorYard[] = [
    {
      id: 1,
      name: 'Двор 1',
      buildings: [
        {
          id: 1,
          address: 'ул. Мира, д. 5',
          elevators: [
            makePublicElevator(),
            makePublicElevator({ elevator_number: 2, status: 'under_repair', status_since: '2026-09-01T09:00:00Z', label: 'ул. Мира, д. 5, подъезд 1, лифт 2' }),
          ],
        },
        {
          id: 2,
          address: 'ул. Мира, д. 3',
          elevators: [makePublicElevator({ status: 'not_working', label: 'ул. Мира, д. 3, подъезд 1, лифт 1' })],
        },
      ],
    },
    {
      id: 2,
      name: 'Двор 2',
      buildings: [
        {
          id: 3,
          address: 'ул. Садовая, д. 1',
          elevators: [
            makePublicElevator({ status: 'maintenance', label: 'ул. Садовая, д. 1, подъезд 1, лифт 1' }),
            makePublicElevator({ entrance_number: 2, label: 'ул. Садовая, д. 1, подъезд 2, лифт 1' }),
          ],
        },
      ],
    },
  ]
  return makePublicData([], { yards })
}

/** Подменяет msw-хендлер публичного эндпоинта; `seen.value` — принятый ?lang. */
export function servePublicElevators(data: PublicElevatorsData, seen: { value: string | null } = { value: null }) {
  server.use(
    http.get('*/api/v2/public/elevators', ({ request }) => {
      seen.value = new URL(request.url).searchParams.get('lang')
      return HttpResponse.json(data)
    }),
  )
}
