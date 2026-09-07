/**
 * Колонки списка жителей: подпись + поле серверной сортировки.
 *
 * Раздел постраничный (25 строк), поэтому упорядочивает сервер.
 *
 * Сортировка по ФИО идёт по СЫРЫМ полям, а не по строке из ячейки: там ФИО
 * собирается `usePersonName` с учётом настройки «заглавными» и подстановкой
 * «Без имени», и порядок зависел бы от оформления. Фамилия первична — список
 * ищут глазами именно по ней.
 *
 * Без `serverField` остались «Адрес» и «Квартир»: оба собираются отдельными
 * запросами уже после выборки страницы, упорядочить по ним всю выборку нельзя.
 */
import type { ResidentListItem } from '../../types/api'
import type { SortableColumn } from '../../utils/tableSort'

export type ResidentColumn = SortableColumn<ResidentListItem> & { labelKey: string }

export const RESIDENT_COLUMNS: readonly ResidentColumn[] = [
  { id: 'name', labelKey: 'residents.headerResident', kind: 'text', serverField: 'name' },
  { id: 'address', labelKey: 'residents.headerAddress', kind: 'text' },
  { id: 'apartments', labelKey: 'residents.headerApartments', kind: 'number' },
  // «По возрастанию» — сначала то, что требует внимания менеджера.
  { id: 'verification', labelKey: 'residents.headerVerification', kind: 'enum', serverField: 'verification' },
  { id: 'status', labelKey: 'residents.headerStatus', kind: 'enum', serverField: 'status' },
]

export const RESIDENTS_SORT_STORAGE_KEY = 'residents_sort_v1'
