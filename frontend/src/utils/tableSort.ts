/**
 * Сортировка таблиц дашборда: описание колонок, компараторы, состояние.
 *
 * Модуль чистый (без React) и тестируется напрямую — образец
 * `components/elevators-public/publicElevatorsFilter.ts`.
 *
 * Два правила, ради которых он и существует:
 *
 * 1. Сортируем СЫРОЕ значение строки, а не то, что нарисовано в ячейке.
 *    В ячейках живут `97 %`, `#10`, `● Активен`, `07 сен 2026` и
 *    локализованные ярлыки — сравнение таких строк даёт мусор
 *    (`100 % < 97 %`, `#10 < #9`, порядок статусов зависит от языка).
 * 2. Колонка без `value` не сортируется вовсе: «Действия», «Флаги» и
 *    составные ячейки просто не получают кнопку в заголовке.
 */

export type SortDirection = 'asc' | 'desc'

export interface SortState {
  columnId: string
  direction: SortDirection
}

export type SortValue = string | number | null | undefined

export type SortKind = 'text' | 'number' | 'date' | 'money' | 'enum'

export interface SortableColumn<T> {
  /** Канон-идентификатор колонки: попадает в localStorage и в запрос к API. */
  id: string
  kind: SortKind
  /** Сырое значение строки. Нет — колонка не сортируется в браузере. */
  value?: (row: T) => SortValue
  /** Имя поля для серверной сортировки. Нет — колонка не сортируется на сервере. */
  serverField?: string
  /** Только для `kind: 'enum'` — явный порядок канон-ключей. */
  order?: readonly string[]
  /** Направление первого клика. По умолчанию `asc`. */
  defaultDirection?: SortDirection
}

/**
 * Один экземпляр на модуль: конструктор `Intl.Collator` дорогой, а вызывается
 * компаратор на каждое сравнение. Локаль зафиксирована, чтобы порядок строк не
 * менялся при переключении интерфейса между ru и uz — данные (ФИО, адреса)
 * остаются одними и теми же. `numeric` даёт человеческую нумерацию
 * (1, 2, 10, 100 вместо 1, 10, 100, 2), `sensitivity: 'base'` игнорирует
 * регистр и диакритику.
 */
const naturalOrder = new Intl.Collator('ru', { numeric: true, sensitivity: 'base' })

/**
 * Приводит значение к сравнимому виду: текст к строке, всё остальное к числу.
 * `null` означает «значения нет» — такие строки всегда уходят в конец списка,
 * независимо от направления. Ноль пустым НЕ считается.
 */
function normalize<T>(column: SortableColumn<T>, raw: SortValue): string | number | null {
  if (raw === null || raw === undefined) return null
  switch (column.kind) {
    case 'text': {
      const text = String(raw).trim()
      return text === '' ? null : text
    }
    case 'number':
    case 'money': {
      if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null
      // `Number('')` — это 0, а не NaN: пустую строку надо отсечь до приведения,
      // иначе строка без суммы встанет между отрицательным долгом и предоплатой.
      const text = String(raw).trim()
      if (text === '') return null
      const num = Number(text)
      return Number.isFinite(num) ? num : null
    }
    case 'date': {
      const ms = Date.parse(String(raw))
      return Number.isNaN(ms) ? null : ms
    }
    case 'enum': {
      const index = (column.order ?? []).indexOf(String(raw))
      return index === -1 ? null : index
    }
  }
}

function compareNormalized(a: string | number, b: string | number): number {
  if (typeof a === 'string' && typeof b === 'string') return naturalOrder.compare(a, b)
  return Number(a) - Number(b)
}

/** Сравнение по одной колонке. Пустые — в конец в обе стороны, равные — 0. */
function compareBy<T>(column: SortableColumn<T>, direction: SortDirection): (a: T, b: T) => number {
  const read = column.value
  if (!read) return () => 0
  const sign = direction === 'desc' ? -1 : 1
  return (a, b) => {
    const left = normalize(column, read(a))
    const right = normalize(column, read(b))
    if (left === null && right === null) return 0
    // Знак направления к пустоте НЕ применяется: строки без значения не должны
    // всплывать наверх при перевороте — там их принимают за максимум.
    if (left === null) return 1
    if (right === null) return -1
    return compareNormalized(left, right) * sign
  }
}

/**
 * Новый упорядоченный массив. Вход не мутируется (правило иммутабельности).
 *
 * Без сортировки и без `defaultCompare` возвращается ТОТ ЖЕ массив — чтобы не
 * ломать ссылочное равенство в зависимостях `useMemo`.
 *
 * Ключи применяются по очереди: выбранная колонка → `defaultCompare` (порядок
 * раздела по умолчанию) → `id` по возрастанию. Последний обязателен: без него
 * строки с одинаковым значением меняются местами при каждом обновлении данных,
 * а на постраничных списках это ещё и теряет строки между страницами.
 */
export function sortRows<T extends { id: number }>(
  rows: readonly T[],
  columns: readonly SortableColumn<T>[],
  sort: SortState | null,
  defaultCompare?: (a: T, b: T) => number,
): T[] {
  const column = sort ? columns.find(c => c.id === sort.columnId) : undefined
  const primary = column?.value && sort ? compareBy(column, sort.direction) : null
  if (!primary) {
    return defaultCompare ? [...rows].sort(defaultCompare) : (rows as T[])
  }
  return [...rows].sort(
    (a, b) => primary(a, b) || (defaultCompare ? defaultCompare(a, b) : 0) || a.id - b.id,
  )
}

// ---------------------------------------------------------------------------
// Состояние
// ---------------------------------------------------------------------------

const DIRECTIONS: readonly string[] = ['asc', 'desc']

/** Формат хранения — `"columnId:direction"`. Читается глазами в devtools. */
export function serializeSortState(sort: SortState): string {
  return `${sort.columnId}:${sort.direction}`
}

/**
 * Разбор сохранённого значения. Мусор, неизвестная колонка и чужое направление
 * дают `null` — страница открывается без сортировки, а не падает.
 */
export function parseSortState(raw: string | null | undefined, columnIds: readonly string[]): SortState | null {
  if (!raw) return null
  const parts = raw.split(':')
  if (parts.length !== 2) return null
  const [columnId, direction] = parts
  if (!columnIds.includes(columnId) || !DIRECTIONS.includes(direction)) return null
  return { columnId, direction: direction as SortDirection }
}

/**
 * Клик по заголовку: своё направление → переворот → порядок по умолчанию.
 *
 * Третье состояние обязательно: порядок по умолчанию содержателен (лифты идут
 * по адресу, подъезду и номеру сразу, жители — по дате создания, которой нет
 * среди колонок) и никакой колонкой не воспроизводится. Без него сохранённая
 * сортировка становится ловушкой — из неё не выйти ни перезагрузкой, ни завтра.
 */
export function nextSortState<T>(current: SortState | null, column: SortableColumn<T>): SortState | null {
  const first = column.defaultDirection ?? 'asc'
  if (current?.columnId !== column.id) return { columnId: column.id, direction: first }
  if (current.direction === first) return { columnId: column.id, direction: first === 'asc' ? 'desc' : 'asc' }
  return null
}
