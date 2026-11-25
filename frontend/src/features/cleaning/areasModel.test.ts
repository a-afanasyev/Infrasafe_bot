import { describe, expect, it } from 'vitest'
import { type AreasDraftRow, ALL_ENTRANCES, areasFromDraft, draftFromAreas, emptyRow } from './areasModel'

const row = (over: Partial<AreasDraftRow> = {}): AreasDraftRow => ({ ...emptyRow(ALL_ENTRANCES), ...over })

describe('areasModel', () => {
  it('черновик из пустых площадей — одна строка «все подъезды»', () => {
    expect(draftFromAreas(null)).toEqual([emptyRow(ALL_ENTRANCES)])
  })

  it('раскладывает 1-й, −1 и особые этажи по полям и собирает обратно', () => {
    const areas = {
      entrances: {
        '*': { typical: 20, floors: { '1': 60, '-1': 80, '16': 31, '30': 28.5 }, points: { fire_stairs: 36 } },
        '3': { typical: 30 },
      },
    }
    const draft = draftFromAreas(areas)
    expect(draft[0]).toMatchObject({ scope: '*', typical: '20', floor1: '60', basement: '80', special: '16:31; 30:28.5' })
    expect(draft[0].points.fire_stairs).toBe('36')
    expect(draft[1]).toMatchObject({ scope: '3', typical: '30', floor1: '' })
    expect(areasFromDraft(draft)).toEqual({ areas })
  })

  it('все поля пустые — площади убираются (null)', () => {
    expect(areasFromDraft([row()])).toEqual({ areas: null })
  })

  it('пустые поля подъезда не попадают в JSON — наследуются от «*»', () => {
    expect(areasFromDraft([row({ typical: '20' }), row({ scope: '2' })])).toEqual({
      areas: { entrances: { '*': { typical: 20 } } },
    })
  })

  it.each([
    [{ typical: 'abc' }, 'badNumber'],
    [{ typical: '-1' }, 'badNumber'],
    [{ typical: '10001' }, 'badNumber'],
    [{ typical: '20', special: '16=31' }, 'badSpecial'],
    [{ typical: '20', special: '0:31' }, 'badSpecial'],
  ])('отказ на %o', (over, error) => {
    expect(areasFromDraft([row(over)])).toEqual({ error })
  })

  it('десятичная запятая принимается', () => {
    expect(areasFromDraft([row({ typical: '20,5' })])).toEqual({ areas: { entrances: { '*': { typical: 20.5 } } } })
  })
})
