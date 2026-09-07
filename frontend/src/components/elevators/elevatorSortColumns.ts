/**
 * Колонки реестра лифтов: подпись + поле серверной сортировки.
 *
 * Список постраничный (50 строк), поэтому упорядочивает СЕРВЕР — в браузере
 * переставились бы только загруженные строки, и «лифт с наибольшим числом
 * заявок» оказался бы максимумом внутри случайных пятидесяти.
 *
 * Колонки без `serverField` заголовком не кликаются:
 * * «Доступность 30д» считается по журналу событий в Python — честной
 *   сортировки по всей выборке для неё сейчас нет;
 * * «Флаги» — три независимых признака, полного порядка у них нет;
 * * «Действия» — не данные.
 */
import type { ElevatorCard } from '../../types/elevators'
import type { SortableColumn } from '../../utils/tableSort'

export type ElevatorColumn = SortableColumn<ElevatorCard> & { labelKey: string }

export const ELEVATOR_COLUMNS: readonly ElevatorColumn[] = [
  { id: 'label', labelKey: 'elevators.columns.label', kind: 'text', serverField: 'label' },
  // «По возрастанию» для статуса — по тяжести: сначала то, что не работает.
  { id: 'status', labelKey: 'elevators.columns.status', kind: 'enum', serverField: 'status' },
  {
    id: 'since',
    labelKey: 'elevators.columns.since',
    kind: 'date',
    serverField: 'status_since',
    defaultDirection: 'desc',
  },
  { id: 'availability', labelKey: 'elevators.columns.availability', kind: 'number' },
  { id: 'flags', labelKey: 'elevators.columns.flags', kind: 'text' },
  {
    id: 'open_requests',
    labelKey: 'elevators.columns.openRequests',
    kind: 'number',
    serverField: 'open_requests',
    defaultDirection: 'desc',
  },
  { id: 'actions', labelKey: 'elevators.columns.actions', kind: 'text' },
]

export const ELEVATORS_SORT_STORAGE_KEY = 'elevators_sort_v1'
