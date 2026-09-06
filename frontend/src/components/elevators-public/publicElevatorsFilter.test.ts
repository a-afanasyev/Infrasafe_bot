import { describe, it, expect } from 'vitest'
import {
  applyFilter,
  buildingCounts,
  countByStatus,
  EMPTY_FILTER,
  parseFilter,
  serializeFilter,
  summaryOf,
} from './publicElevatorsFilter'
import { EMPTY_PUBLIC_DATA, makeTwoYardsData } from '../../test/fixtures/publicElevators'

const yards = makeTwoYardsData().yards

function labels(result: ReturnType<typeof applyFilter>): string[] {
  return result.flatMap((y) => y.buildings.flatMap((b) => b.elevators.map((e) => e.label)))
}

describe('parseFilter / serializeFilter — состояние фильтров в URL', () => {
  it('читает status/q/yard (q — как есть, пробелы не режем: иначе не набрать «ул. Мира»), отбрасывая неизвестный статус и нечисловой двор', () => {
    expect(parseFilter(new URLSearchParams('status=under_repair&q=%20Мира%20&yard=2'))).toEqual({
      status: 'under_repair', q: ' Мира ', yard: 2,
    })
    expect(parseFilter(new URLSearchParams('status=bogus&yard=abc'))).toEqual(EMPTY_FILTER)
    expect(parseFilter(new URLSearchParams(''))).toEqual(EMPTY_FILTER)
  })

  it('сериализует только непустые поля', () => {
    expect(serializeFilter(EMPTY_FILTER).toString()).toBe('')
    expect(serializeFilter({ status: 'working', q: '', yard: null }).toString()).toBe('status=working')
    expect(serializeFilter({ status: null, q: 'сад', yard: 2 }).toString()).toBe(`q=${encodeURIComponent('сад')}&yard=2`)
  })
})

describe('applyFilter', () => {
  it('без фильтров возвращает всё', () => {
    expect(labels(applyFilter(yards, EMPTY_FILTER))).toHaveLength(5)
  })

  it('статус сужает до лифтов этого статуса и выбрасывает опустевшие дома и дворы', () => {
    const result = applyFilter(yards, { ...EMPTY_FILTER, status: 'under_repair' })
    expect(labels(result)).toEqual(['ул. Мира, д. 5, подъезд 1, лифт 2'])
    expect(result.map((y) => y.name)).toEqual(['Двор 1'])
    expect(result[0].buildings.map((b) => b.address)).toEqual(['ул. Мира, д. 5'])
  })

  it('поиск — по адресу дома без регистра; совпадение по имени двора оставляет весь двор', () => {
    expect(labels(applyFilter(yards, { ...EMPTY_FILTER, q: 'САДОВ' }))).toEqual([
      'ул. Садовая, д. 1, подъезд 1, лифт 1',
      'ул. Садовая, д. 1, подъезд 2, лифт 1',
    ])
    expect(labels(applyFilter(yards, { ...EMPTY_FILTER, q: 'д. 3' }))).toEqual(['ул. Мира, д. 3, подъезд 1, лифт 1'])
    expect(labels(applyFilter(yards, { ...EMPTY_FILTER, q: 'двор 2' }))).toHaveLength(2)
    expect(applyFilter(yards, { ...EMPTY_FILTER, q: 'нет такого' })).toEqual([])
  })

  it('двор + статус комбинируются', () => {
    expect(labels(applyFilter(yards, { status: 'working', q: '', yard: 2 }))).toEqual(['ул. Садовая, д. 1, подъезд 2, лифт 1'])
    expect(applyFilter(yards, { status: 'not_working', q: '', yard: 2 })).toEqual([])
  })
})

describe('countByStatus / buildingCounts', () => {
  it('считает сводку по переданным дворам', () => {
    expect(countByStatus(yards)).toEqual({ total: 5, working: 2, not_working: 1, under_repair: 1, maintenance: 1 })
    expect(countByStatus([])).toEqual({ total: 0, working: 0, not_working: 0, under_repair: 0, maintenance: 0 })
  })

  it('summaryOf: без поля summary (старый API при раскате фронта раньше) — досчёт по yards; с полем — серверные значения; до загрузки — нули', () => {
    const data = makeTwoYardsData()
    const derived = { total: 5, working: 2, not_working: 1, under_repair: 1, maintenance: 1 }
    expect(summaryOf({ ...data, summary: undefined })).toEqual(derived)
    // Серверная сводка побеждает, даже если расходится с yards (кэш на сервере — источник истины).
    const server = { total: 100, working: 84, not_working: 10, under_repair: 4, maintenance: 2 }
    expect(summaryOf({ ...data, summary: server })).toEqual(server)
    expect(summaryOf(undefined)).toEqual(EMPTY_PUBLIC_DATA.summary)
  })

  it('считает «работают / всего» по каждому дому', () => {
    expect(buildingCounts(yards)).toEqual({ 1: { working: 1, total: 2 }, 2: { working: 0, total: 1 }, 3: { working: 1, total: 2 } })
  })
})
