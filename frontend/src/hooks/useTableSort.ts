/**
 * Состояние сортировки таблицы с памятью в браузере пользователя.
 *
 * Хук один на оба режима: таблицы, чьи данные загружены целиком, вызывают
 * `sortRows`; постраничные отдают `queryParams` в запрос, чтобы сервер
 * упорядочил ВСЮ выборку, а не загруженную страницу.
 */
import { useCallback, useMemo, useState } from 'react'

import {
  nextSortState,
  parseSortState,
  serializeSortState,
  sortRows as sortRowsPure,
  type SortableColumn,
  type SortDirection,
  type SortState,
} from '../utils/tableSort'

export interface TableSortQuery {
  sort?: string
  order?: SortDirection
}

export interface UseTableSortResult<T> {
  /** Действующая сортировка; `null` — порядок по умолчанию. */
  sort: SortState | null
  toggle: (columnId: string) => void
  clear: () => void
  direction: (columnId: string) => SortDirection | null
  ariaSort: (columnId: string) => 'ascending' | 'descending' | 'none'
  /** Клиентский режим: упорядоченная копия строк. */
  sortRows: (rows: readonly T[]) => T[]
  /** Серверный режим: параметры для запроса списка. */
  queryParams: TableSortQuery
}

/** Значение сохранённое, но не применимое, читается заново — см. `visible`. */
function read(storageKey: string): SortState | null {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return null
    const parts = raw.split(':')
    return parts.length === 2 ? { columnId: parts[0], direction: parts[1] as SortDirection } : null
  } catch {
    return null
  }
}

function write(storageKey: string, sort: SortState | null): void {
  try {
    if (sort) localStorage.setItem(storageKey, serializeSortState(sort))
    else localStorage.removeItem(storageKey)
  } catch {
    // Приватный режим или переполненное хранилище: сортировка работает,
    // просто не переживёт перезагрузку. Ронять страницу из-за этого незачем.
  }
}

export function useTableSort<T extends { id: number }>(
  columns: readonly SortableColumn<T>[],
  storageKey: string,
  /** Порядок раздела при отсутствии сортировки; он же вторичный ключ. */
  defaultCompare?: (a: T, b: T) => number,
): UseTableSortResult<T> {
  // Ленивая инициализация: до первого клика в хранилище не пишем — иначе
  // страница с урезанным набором колонок затирала бы чужое значение.
  const [stored, setStored] = useState<SortState | null>(() => read(storageKey))

  const columnIds = useMemo(() => columns.map(c => c.id), [columns])

  /**
   * Наружу отдаём сортировку, только если её колонка сейчас на экране. Набор
   * колонок бывает условным (баланс квартиры появляется вместе с модулем
   * платежей), и запись мы при этом НЕ чистим: вернётся колонка — вернётся и
   * сортировка. Разбор идёт через общий валидатор, поэтому мусор в хранилище
   * отсекается тем же правилом.
   */
  const sort = useMemo(
    () => (stored ? parseSortState(serializeSortState(stored), columnIds) : null),
    [stored, columnIds],
  )

  const toggle = useCallback(
    (columnId: string) => {
      const column = columns.find(c => c.id === columnId)
      if (!column || (!column.value && !column.serverField)) return
      const next = nextSortState(sort, column)
      setStored(next)
      write(storageKey, next)
    },
    [columns, sort, storageKey],
  )

  const clear = useCallback(() => {
    setStored(null)
    write(storageKey, null)
  }, [storageKey])

  const direction = useCallback(
    (columnId: string) => (sort?.columnId === columnId ? sort.direction : null),
    [sort],
  )

  const ariaSort = useCallback(
    (columnId: string): 'ascending' | 'descending' | 'none' => {
      const dir = sort?.columnId === columnId ? sort.direction : null
      return dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none'
    },
    [sort],
  )

  const sortRows = useCallback(
    (rows: readonly T[]) => sortRowsPure(rows, columns, sort, defaultCompare),
    [columns, sort, defaultCompare],
  )

  const queryParams = useMemo<TableSortQuery>(() => {
    const field = sort ? columns.find(c => c.id === sort.columnId)?.serverField : undefined
    return field ? { sort: field, order: sort!.direction } : {}
  }, [columns, sort])

  return { sort, toggle, clear, direction, ariaSort, sortRows, queryParams }
}
