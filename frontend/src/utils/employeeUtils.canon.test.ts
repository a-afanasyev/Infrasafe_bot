import { describe, it, expect } from 'vitest'
import { SPEC_COLORS, SPEC_EMOJI } from './employeeUtils'
import { SPECIALIZATIONS } from '@/constants/specializations'

// Фильтр на странице «Сотрудники» строился из `Object.keys(SPEC_COLORS)` —
// это была ПЯТАЯ копия списка специализаций, и «Ремонт / разнорабочий» в неё не
// попал: сотрудника с такой специализацией нельзя было отфильтровать.
//
// Теперь фильтр берёт канон, а эти карты отвечают только за оформление. Тест
// держит их полными, чтобы новая специализация не появилась в фильтре
// бесцветной и без иконки.

describe('оформление специализаций покрывает канон', () => {
  it.each(SPECIALIZATIONS)('у «%s» есть цвет', (spec) => {
    expect(SPEC_COLORS[spec]).toBeTruthy()
  })

  it.each(SPECIALIZATIONS)('у «%s» есть иконка', (spec) => {
    expect(SPEC_EMOJI[spec]).toBeTruthy()
  })

  it('в картах оформления нет значений вне канона', () => {
    // Иначе фильтр показал бы позицию, которую невозможно назначить.
    const canon = new Set<string>(SPECIALIZATIONS)
    expect(Object.keys(SPEC_COLORS).filter(k => !canon.has(k))).toEqual([])
    expect(Object.keys(SPEC_EMOJI).filter(k => !canon.has(k))).toEqual([])
  })
})
