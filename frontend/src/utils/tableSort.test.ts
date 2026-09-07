import { describe, expect, it } from 'vitest'

import {
  nextSortState,
  parseSortState,
  serializeSortState,
  sortRows,
  type SortableColumn,
} from './tableSort'

interface Row {
  id: number
  name?: string | null
  count?: number | null
  when?: string | null
  money?: string | null
  status?: string | null
}

const byName: SortableColumn<Row> = { id: 'name', kind: 'text', value: r => r.name }
const byCount: SortableColumn<Row> = { id: 'count', kind: 'number', value: r => r.count }
const byWhen: SortableColumn<Row> = { id: 'when', kind: 'date', value: r => r.when, defaultDirection: 'desc' }
const byMoney: SortableColumn<Row> = { id: 'money', kind: 'money', value: r => r.money }
const byStatus: SortableColumn<Row> = {
  id: 'status',
  kind: 'enum',
  value: r => r.status,
  order: ['working', 'not_working', 'under_repair'],
}
const COLUMNS = [byName, byCount, byWhen, byMoney, byStatus]

/** Порядок id после сортировки — то, что реально видит пользователь. */
function ids(rows: Row[], columnId: string, direction: 'asc' | 'desc'): number[] {
  return sortRows(rows, COLUMNS, { columnId, direction }).map(r => r.id)
}

describe('sortRows — текст', () => {
  const rows: Row[] = [
    { id: 1, name: '10' },
    { id: 2, name: '2' },
    { id: 3, name: '100' },
    { id: 4, name: '1' },
  ]

  it('нумерует по-человечески: 1, 2, 10, 100', () => {
    expect(ids(rows, 'name', 'asc')).toEqual([4, 2, 1, 3])
  })

  it('переворачивает порядок', () => {
    expect(ids(rows, 'name', 'desc')).toEqual([3, 1, 2, 4])
  })

  it('не различает регистр — равные значения идут по id', () => {
    const mixed: Row[] = [
      { id: 2, name: 'ЛИФТ' },
      { id: 1, name: 'лифт' },
    ]
    expect(ids(mixed, 'name', 'asc')).toEqual([1, 2])
    expect(ids(mixed, 'name', 'desc')).toEqual([1, 2])
  })
})

describe('sortRows — числа, даты, деньги', () => {
  it('сравнивает числа как числа, ноль не считается пустым', () => {
    const rows: Row[] = [
      { id: 1, count: 10 },
      { id: 2, count: 0 },
      { id: 3, count: 9 },
      { id: 4, count: -5 },
    ]
    expect(ids(rows, 'count', 'asc')).toEqual([4, 2, 3, 1])
  })

  it('сравнивает даты как моменты времени, а не строки', () => {
    const rows: Row[] = [
      { id: 1, when: '2026-01-09T10:00:00Z' },
      { id: 2, when: '2026-01-10T09:00:00Z' },
      { id: 3, when: '2025-12-31T23:00:00Z' },
    ]
    expect(ids(rows, 'when', 'asc')).toEqual([3, 1, 2])
  })

  it('сравнивает денежные строки как числа', () => {
    const rows: Row[] = [
      { id: 1, money: '9' },
      { id: 2, money: '10' },
      { id: 3, money: '-230491.94' },
    ]
    expect(ids(rows, 'money', 'asc')).toEqual([3, 1, 2])
  })

  it('перечисление идёт заданным порядком, а не алфавитом', () => {
    const rows: Row[] = [
      { id: 1, status: 'under_repair' },
      { id: 2, status: 'working' },
      { id: 3, status: 'not_working' },
    ]
    expect(ids(rows, 'status', 'asc')).toEqual([2, 3, 1])
  })
})

describe('sortRows — пустые значения', () => {
  const cases: Array<[string, Row[]]> = [
    ['name', [{ id: 1, name: 'a' }, { id: 2, name: null }, { id: 3, name: '   ' }]],
    ['count', [{ id: 1, count: 5 }, { id: 2, count: null }, { id: 3 }]],
    ['when', [{ id: 1, when: '2026-01-01T00:00:00Z' }, { id: 2, when: 'не дата' }, { id: 3, when: null }]],
    ['money', [{ id: 1, money: '1' }, { id: 2, money: '' }, { id: 3, money: null }]],
    ['status', [{ id: 1, status: 'working' }, { id: 2, status: 'выдумка' }, { id: 3, status: null }]],
  ]

  it.each(cases)('колонка %s: пустые внизу при возрастании', (columnId, rows) => {
    expect(ids(rows, columnId, 'asc')).toEqual([1, 2, 3])
  })

  it.each(cases)('колонка %s: пустые остаются внизу и при убывании', (columnId, rows) => {
    expect(ids(rows, columnId, 'desc')).toEqual([1, 2, 3])
  })
})

describe('sortRows — устойчивость и чистота', () => {
  const rows: Row[] = [
    { id: 3, count: 1 },
    { id: 1, count: 1 },
    { id: 2, count: 1 },
  ]

  it('равные значения упорядочены по id и не перемешиваются при перевороте', () => {
    expect(ids(rows, 'count', 'asc')).toEqual([1, 2, 3])
    expect(ids(rows, 'count', 'desc')).toEqual([1, 2, 3])
  })

  it('не мутирует входной массив', () => {
    const source: Row[] = [{ id: 2, count: 5 }, { id: 1, count: 9 }]
    const before = [...source]
    sortRows(source, COLUMNS, { columnId: 'count', direction: 'asc' })
    expect(source).toEqual(before)
  })

  it('без сортировки возвращает тот же массив, не копию', () => {
    const source: Row[] = [{ id: 1 }]
    expect(sortRows(source, COLUMNS, null)).toBe(source)
  })

  it('неизвестная колонка не меняет порядок', () => {
    const source: Row[] = [{ id: 2 }, { id: 1 }]
    expect(sortRows(source, COLUMNS, { columnId: 'выдумка', direction: 'asc' })).toBe(source)
  })

  it('порядок по умолчанию применяется, когда сортировки нет', () => {
    const source: Row[] = [{ id: 2 }, { id: 1 }]
    const result = sortRows(source, COLUMNS, null, (a, b) => a.id - b.id)
    expect(result.map(r => r.id)).toEqual([1, 2])
    expect(result).not.toBe(source)
  })

  it('порядок по умолчанию служит вторичным ключом', () => {
    const source: Row[] = [
      { id: 1, count: 1, name: 'b' },
      { id: 2, count: 1, name: 'a' },
    ]
    const byNameAsc = (a: Row, b: Row) => (a.name ?? '').localeCompare(b.name ?? '')
    const result = sortRows(source, COLUMNS, { columnId: 'count', direction: 'asc' }, byNameAsc)
    expect(result.map(r => r.id)).toEqual([2, 1])
  })
})

describe('parseSortState', () => {
  const ids_ = ['name', 'count']

  it('читает корректное значение', () => {
    expect(parseSortState('name:desc', ids_)).toEqual({ columnId: 'name', direction: 'desc' })
  })

  it.each([
    ['пусто', null],
    ['пустая строка', ''],
    ['без разделителя', 'name'],
    ['неизвестная колонка', 'выдумка:asc'],
    ['чужое направление', 'name:вверх'],
    ['лишние части', 'name:asc:extra'],
  ])('%s → без сортировки', (_label, raw) => {
    expect(parseSortState(raw, ids_)).toBeNull()
  })

  it('сериализация обратима', () => {
    const state = { columnId: 'count', direction: 'asc' } as const
    expect(parseSortState(serializeSortState(state), ids_)).toEqual(state)
  })
})

describe('nextSortState', () => {
  it('первый клик по колонке даёт её направление по умолчанию', () => {
    expect(nextSortState(null, byName)).toEqual({ columnId: 'name', direction: 'asc' })
    expect(nextSortState(null, byWhen)).toEqual({ columnId: 'when', direction: 'desc' })
  })

  it('второй клик переворачивает', () => {
    expect(nextSortState({ columnId: 'name', direction: 'asc' }, byName)).toEqual({
      columnId: 'name',
      direction: 'desc',
    })
    expect(nextSortState({ columnId: 'when', direction: 'desc' }, byWhen)).toEqual({
      columnId: 'when',
      direction: 'asc',
    })
  })

  it('третий клик возвращает порядок по умолчанию', () => {
    expect(nextSortState({ columnId: 'name', direction: 'desc' }, byName)).toBeNull()
    expect(nextSortState({ columnId: 'when', direction: 'asc' }, byWhen)).toBeNull()
  })

  it('клик по другой колонке начинает её цикл заново', () => {
    expect(nextSortState({ columnId: 'name', direction: 'desc' }, byCount)).toEqual({
      columnId: 'count',
      direction: 'asc',
    })
  })
})
