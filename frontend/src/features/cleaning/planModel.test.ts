import { describe, expect, it } from 'vitest'
import {
  type DraftItem,
  coverage,
  draftFrom,
  parseEntrances,
  splitInHalf,
  toPayload,
  toggleDay,
  validate,
  weekPreview,
} from './planModel'

const item = (over: Partial<DraftItem> = {}): DraftItem => ({
  work_kind: 'wet', weekdays: [0, 2, 4], entrances: '', floors: 'all', floor_from: '', floor_to: '', ...over,
})

describe('planModel', () => {
  it('toggleDay добавляет и убирает день, сохраняя порядок', () => {
    expect(toggleDay([0, 4], 2)).toEqual([0, 2, 4])
    expect(toggleDay([0, 2, 4], 2)).toEqual([0, 4])
  })

  it('parseEntrances: пусто — все подъезды, иначе список; мусор — ошибка', () => {
    expect(parseEntrances('')).toBeNull()
    expect(parseEntrances(' 1, 3 ')).toEqual([1, 3])
    expect(parseEntrances('1 и 3')).toBe('invalid')
  })

  it('toPayload собирает пункты плана для API', () => {
    const payload = toPayload([
      item(),
      item({ work_kind: 'dry', weekdays: [1], floors: 'first' }),
      item({ weekdays: [3], floors: 'range', floor_from: '6', floor_to: '9', entrances: '1,3' }),
      item({ work_kind: 'elevator', weekdays: [0] }),
    ])
    expect(payload).toEqual([
      { work_kind: 'wet', weekdays: [0, 2, 4] },
      { work_kind: 'dry', weekdays: [1], floor_from: 1, floor_to: 1 },
      { work_kind: 'wet', weekdays: [3], floor_from: 6, floor_to: 9, entrances: [1, 3] },
      { work_kind: 'elevator', weekdays: [0] },
    ])
  })

  it('draftFrom обратен toPayload', () => {
    const drafts = [
      item(),
      item({ work_kind: 'dry', weekdays: [1], floors: 'first' }),
      item({ weekdays: [3], floors: 'range', floor_from: '6', floor_to: '9', entrances: '1, 3' }),
    ]
    expect(draftFrom(toPayload(drafts))).toEqual(drafts)
  })

  it('validate ловит пустые дни, плохой отрезок и подъезды', () => {
    expect(validate([item()], 9, 3)).toBeNull()
    expect(validate([], 9, 3)).toBe('empty')
    expect(validate([item({ weekdays: [] })], 9, 3)).toBe('weekdays')
    expect(validate([item({ floors: 'range', floor_from: '5', floor_to: '2' })], 9, 3)).toBe('floors')
    expect(validate([item({ floors: 'range', floor_from: '1', floor_to: '12' })], 9, 3)).toBe('floors')
    expect(validate([item({ entrances: '4' })], 9, 3)).toBe('entrances')
  })

  it('splitInHalf делит работу на две строки с чередованием дней', () => {
    const [low, high] = splitInHalf(item({ weekdays: [0, 1, 3, 4] }), 9)
    expect([low.floor_from, low.floor_to, low.weekdays]).toEqual(['1', '5', [0, 3]])
    expect([high.floor_from, high.floor_to, high.weekdays]).toEqual(['6', '9', [1, 4]])
    expect(low.floors).toBe('range')
  })

  it('coverage считает проходы по этажам за неделю', () => {
    const items = [
      item({ weekdays: [0, 3], floors: 'range', floor_from: '1', floor_to: '5' }),
      item({ weekdays: [1], floors: 'range', floor_from: '6', floor_to: '8' }),
    ]
    expect(coverage(items, 'wet', 9)).toEqual([2, 2, 2, 2, 2, 1, 1, 1, 0])
    // строка только на подъезд 1 не закрывает этажи подъезда 2
    const first = [item({ weekdays: [0, 3], entrances: '1' })]
    expect(coverage(first, 'wet', 3, 1)).toEqual([2, 2, 2])
    expect(coverage(first, 'wet', 3, 2)).toEqual([0, 0, 0])
  })

  it('weekPreview: работы и этажи по дням, счёт этажей на подъезд', () => {
    const days = weekPreview([
      item({ weekdays: [0], floors: 'range', floor_from: '1', floor_to: '5' }),
      item({ work_kind: 'elevator', weekdays: [0, 1] }),
    ], 9)
    expect(days[0]).toEqual({ works: [{ kind: 'wet', from: 1, to: 5 }, { kind: 'elevator' }], floors: 5 })
    expect(days[1]).toEqual({ works: [{ kind: 'elevator' }], floors: 0 })
    expect(days[6]).toEqual({ works: [], floors: 0 })
  })
})
