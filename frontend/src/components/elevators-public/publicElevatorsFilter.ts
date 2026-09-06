import { ELEVATOR_STATUSES, type ElevatorStatus } from '../../types/elevators'
import type { PublicElevatorYard, PublicElevatorsData, PublicElevatorsSummary } from '../../hooks/usePublicElevators'
import { EMPTY_SUMMARY } from './publicElevatorStyles'

// Клиентские фильтры страницы /elevators (T17): состояние живёт в URL-query
// (`?status=&q=&yard=`), чтобы ссылку можно было переслать. Чистые функции,
// без React — тестируются напрямую.

export interface PublicElevatorsFilter {
  status: ElevatorStatus | null
  q: string
  yard: number | null
}

export const EMPTY_FILTER: PublicElevatorsFilter = { status: null, q: '', yard: null }

function isElevatorStatus(value: string | null): value is ElevatorStatus {
  return value != null && (ELEVATOR_STATUSES as readonly string[]).includes(value)
}

/** Неизвестный статус и нечисловой двор → как будто параметра нет; `q` — как есть. */
export function parseFilter(params: URLSearchParams): PublicElevatorsFilter {
  const status = params.get('status')
  const yardRaw = params.get('yard')
  return {
    status: isElevatorStatus(status) ? status : null,
    q: params.get('q') ?? '',
    yard: yardRaw != null && /^\d+$/.test(yardRaw) ? Number(yardRaw) : null,
  }
}

/** Только непустые поля — чистый URL без `?status=&q=`. */
export function serializeFilter(filter: PublicElevatorsFilter): URLSearchParams {
  const params = new URLSearchParams()
  if (filter.status) params.set('status', filter.status)
  if (filter.q) params.set('q', filter.q)
  if (filter.yard != null) params.set('yard', String(filter.yard))
  return params
}

function normalize(text: string): string {
  return text.trim().toLowerCase()
}

/**
 * Двор → дом → лифт: двор по id, поиск по адресу дома без регистра (совпадение
 * по имени двора оставляет все его дома), статус — по лифтам; опустевшие дома
 * и дворы выбрасываются.
 */
export function applyFilter(yards: PublicElevatorYard[], filter: PublicElevatorsFilter): PublicElevatorYard[] {
  const q = normalize(filter.q)
  return yards
    .filter((yard) => filter.yard == null || yard.id === filter.yard)
    .map((yard) => {
      const yardMatches = q === '' || yard.name.toLowerCase().includes(q)
      const buildings = yard.buildings
        .filter((b) => yardMatches || b.address.toLowerCase().includes(q))
        .map((b) => ({
          ...b,
          elevators: filter.status ? b.elevators.filter((e) => e.status === filter.status) : b.elevators,
        }))
        .filter((b) => b.elevators.length > 0)
      return { ...yard, buildings }
    })
    .filter((yard) => yard.buildings.length > 0)
}

/** Сводка по переданным дворам — для счётчиков в чипах в пределах двора/поиска. */
export function countByStatus(yards: PublicElevatorYard[]): PublicElevatorsSummary {
  return yards
    .flatMap((y) => y.buildings.flatMap((b) => b.elevators))
    .reduce<PublicElevatorsSummary>(
      (acc, e) => ({ ...acc, total: acc.total + 1, [e.status]: acc[e.status] + 1 }),
      { ...EMPTY_SUMMARY },
    )
}

/**
 * Сводка ответа: серверная `summary`; без поля (старый API — фронт раскатан раньше
 * API) — досчитываем по `yards`; до загрузки — нули.
 */
export function summaryOf(data: PublicElevatorsData | undefined): PublicElevatorsSummary {
  return data?.summary ?? countByStatus(data?.yards ?? [])
}

export interface BuildingCount {
  working: number
  total: number
}

/** «N из M работают» по каждому дому — по ВСЕМ его лифтам, не по отфильтрованным. */
export function buildingCounts(yards: PublicElevatorYard[]): Record<number, BuildingCount> {
  return Object.fromEntries(
    yards.flatMap((y) => y.buildings).map((b) => [
      b.id,
      { working: b.elevators.filter((e) => e.status === 'working').length, total: b.elevators.length },
    ]),
  )
}
