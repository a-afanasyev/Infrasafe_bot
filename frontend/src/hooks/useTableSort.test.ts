import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SortableColumn } from '../utils/tableSort'
import { useTableSort } from './useTableSort'

interface Row {
  id: number
  name?: string | null
  count?: number | null
}

const KEY = 'test_sort_v1'
const NAME: SortableColumn<Row> = { id: 'name', kind: 'text', value: r => r.name, serverField: 'name' }
const COUNT: SortableColumn<Row> = { id: 'count', kind: 'number', value: r => r.count }
const ACTIONS: SortableColumn<Row> = { id: 'actions', kind: 'text' }
const COLUMNS = [NAME, COUNT, ACTIONS]

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('useTableSort', () => {
  it('открывается без сортировки, когда в хранилище пусто', () => {
    const { result } = renderHook(() => useTableSort(COLUMNS, KEY))
    expect(result.current.sort).toBeNull()
    expect(result.current.ariaSort('name')).toBe('none')
    expect(result.current.queryParams).toEqual({})
  })

  it('поднимает сохранённое значение при открытии страницы', () => {
    localStorage.setItem(KEY, 'name:desc')
    const { result } = renderHook(() => useTableSort(COLUMNS, KEY))
    expect(result.current.sort).toEqual({ columnId: 'name', direction: 'desc' })
    expect(result.current.ariaSort('name')).toBe('descending')
  })

  it('проходит цикл из трёх кликов и чистит запись на третьем', () => {
    const { result } = renderHook(() => useTableSort(COLUMNS, KEY))

    act(() => result.current.toggle('name'))
    expect(result.current.sort).toEqual({ columnId: 'name', direction: 'asc' })
    expect(localStorage.getItem(KEY)).toBe('name:asc')

    act(() => result.current.toggle('name'))
    expect(result.current.direction('name')).toBe('desc')
    expect(localStorage.getItem(KEY)).toBe('name:desc')

    act(() => result.current.toggle('name'))
    expect(result.current.sort).toBeNull()
    expect(localStorage.getItem(KEY)).toBeNull()
  })

  it('игнорирует клик по колонке без ключа сортировки', () => {
    const { result } = renderHook(() => useTableSort(COLUMNS, KEY))
    act(() => result.current.toggle('actions'))
    expect(result.current.sort).toBeNull()
    expect(localStorage.getItem(KEY)).toBeNull()
  })

  it('мусор в хранилище не ломает страницу и не затирается', () => {
    localStorage.setItem(KEY, 'какая-то-дрянь')
    const { result } = renderHook(() => useTableSort(COLUMNS, KEY))
    expect(result.current.sort).toBeNull()
    expect(localStorage.getItem(KEY)).toBe('какая-то-дрянь')
  })

  it('исчезнувшая колонка не сортирует, но запись сохраняется до её возвращения', () => {
    localStorage.setItem(KEY, 'count:asc')
    const { result, rerender } = renderHook(({ cols }) => useTableSort(cols, KEY), {
      initialProps: { cols: [NAME] as SortableColumn<Row>[] },
    })
    expect(result.current.sort).toBeNull()
    expect(localStorage.getItem(KEY)).toBe('count:asc')

    rerender({ cols: COLUMNS })
    expect(result.current.sort).toEqual({ columnId: 'count', direction: 'asc' })
  })

  it('продолжает работать, когда запись в хранилище запрещена', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceeded')
    })
    const { result } = renderHook(() => useTableSort(COLUMNS, KEY))
    act(() => result.current.toggle('name'))
    expect(result.current.sort).toEqual({ columnId: 'name', direction: 'asc' })
  })

  it('сортирует строки и держит порядок по умолчанию вторичным ключом', () => {
    const rows: Row[] = [
      { id: 1, name: 'б', count: 1 },
      { id: 2, name: 'а', count: 1 },
      { id: 3, name: 'в', count: 0 },
    ]
    const byName = (a: Row, b: Row) => (a.name ?? '').localeCompare(b.name ?? '')
    const { result } = renderHook(() => useTableSort(COLUMNS, KEY, byName))

    expect(result.current.sortRows(rows).map(r => r.id)).toEqual([2, 1, 3])
    act(() => result.current.toggle('count'))
    expect(result.current.sortRows(rows).map(r => r.id)).toEqual([3, 2, 1])
  })

  it('отдаёт параметры запроса только для колонок с серверным полем', () => {
    const { result } = renderHook(() => useTableSort(COLUMNS, KEY))

    act(() => result.current.toggle('name'))
    expect(result.current.queryParams).toEqual({ sort: 'name', order: 'asc' })

    act(() => result.current.toggle('count'))
    expect(result.current.queryParams).toEqual({})
  })
})
