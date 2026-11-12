import { describe, expect, it, vi } from 'vitest'
import {
  EMPTY_DRAFT,
  applyIssueFix,
  buildCheckBody,
  buildCreateBody,
  isPhoneComplete,
  residentQuery,
  stepAfter,
  stepBefore,
  withAddress,
  type Draft,
} from './model'

const BUILDING = { level: 'building' as const, id: 4, label: 'Yangi Olmazor, 4G', buildingId: 4 }
const APARTMENT = { level: 'apartment' as const, id: 12, label: 'Yangi Olmazor, 4G, кв. 12', buildingId: 4 }

const filled = (over: Partial<Draft> = {}): Draft => ({
  ...EMPTY_DRAFT,
  phone: '+998 90 111-22-33',
  callerName: 'Азиз',
  address: BUILDING,
  category: 'plumbing',
  description: ' течёт труба ',
  urgency: 'medium',
  ...over,
})

describe('телефон звонящего', () => {
  it('полный номер — от 9 цифр; ищем по последним 9', () => {
    expect(isPhoneComplete('90 111')).toBe(false)
    expect(isPhoneComplete('90 111-22-33')).toBe(true)
    expect(residentQuery('+998 (90) 111-22-33')).toBe('901112233')
  })
})

describe('порядок шагов', () => {
  it('идёт по одному вопросу до проверки и обратно', () => {
    const d = filled()
    expect(stepAfter('phone', d)).toBe('address')
    expect(stepAfter('address', d)).toBe('category')
    expect(stepAfter('category', d)).toBe('description')
    expect(stepAfter('description', d)).toBe('urgency')
    expect(stepAfter('urgency', d)).toBe('review')
    expect(stepBefore('description', d)).toBe('category')
    expect(stepBefore('phone', d)).toBe('phone')
  })

  it('правка из сводки возвращает в сводку', () => {
    const d = filled({ editing: true })
    expect(stepAfter('address', d)).toBe('review')
    expect(stepBefore('description', d)).toBe('review')
  })
})

describe('тело заявки', () => {
  it('звонящий не найден: имя и телефон в примечания, приёмка у менеджера', () => {
    expect(buildCreateBody(filled())).toEqual({
      category: 'plumbing',
      urgency: 'medium',
      description: 'течёт труба',
      building_id: 4,
      caller_name: 'Азиз',
      caller_phone: '+998901112233',
      acceptance_mode: 'manager',
    })
  })

  it('номер без кода страны уходит как введён, без «+»', () => {
    expect(buildCreateBody(filled({ phone: '90 555 00 11' })).caller_phone).toBe('905550011')
  })

  it('житель найден и выбрана его квартира: заявка от его имени', () => {
    const d = filled({
      resident: { id: 7, fullName: 'Resident User' },
      residentApartments: [{ id: 12, label: APARTMENT.label, building_id: 4 }],
      address: APARTMENT,
    })
    expect(buildCreateBody(d)).toEqual({
      category: 'plumbing', urgency: 'medium', description: 'течёт труба', apartment_id: 12, user_id: 7,
    })
  })

  it('житель найден, но квартира чужая: без user_id (иначе сервер отобьёт)', () => {
    const d = filled({
      resident: { id: 7, fullName: 'Resident User' },
      residentApartments: [{ id: 99, label: 'кв. 99', building_id: 4 }],
      address: APARTMENT,
    })
    const body = buildCreateBody(d)
    expect(body.user_id).toBeUndefined()
    expect(body.acceptance_mode).toBe('manager')
    expect(body.caller_name).toBe('Resident User')
  })

  it('житель найден, проблема в доме: заявка всё равно от его имени', () => {
    const d = filled({ resident: { id: 7, fullName: 'Resident User' }, address: BUILDING })
    expect(buildCreateBody(d)).toMatchObject({ building_id: 4, user_id: 7 })
  })

  it('на проверку уходят только поля заявки', () => {
    expect(buildCheckBody(filled())).toEqual({
      category: 'plumbing', urgency: 'medium', description: 'течёт труба', building_id: 4,
    })
  })
})

describe('«Исправить» в одно касание', () => {
  it('категория и срочность берутся из замечания', () => {
    const d = filled({ category: 'electricity' })
    expect(applyIssueFix(d, { field: 'category', code: 'category_mismatch', suggestion: 'plumbing', options: [] }).category).toBe('plumbing')
    expect(applyIssueFix(d, { field: 'urgency', code: 'urgency_low', suggestion: 'high', options: [] }).urgency).toBe('high')
  })

  it('адрес — выбранный вариант справочника', () => {
    const option = { type: 'building' as const, id: 14, yard_id: 1, label: 'Yangi Olmazor, 14G (Olmazor)' }
    const fixed = applyIssueFix(filled(), { field: 'address', code: 'address_mismatch', suggestion: null, options: [option] }, option)
    expect(fixed.address).toEqual({ level: 'building', id: 14, label: option.label, buildingId: 14 })
  })
})

describe('лифт привязан к дому', () => {
  const chosen = { elevatorId: 5, elevatorLabel: 'Лифт 1', elevatorStatus: null, operational: false }

  it('смена дома сбрасывает выбранный лифт, тот же дом — сохраняет', () => {
    const d = filled({ elevator: chosen })
    expect(withAddress(d, APARTMENT).elevator).toEqual(chosen) // тот же дом 4
    expect(withAddress(d, { level: 'building', id: 14, label: '14G', buildingId: 14 }).elevator.elevatorId).toBeNull()
  })

  it('правка из сводки не проходит мимо выбора лифта, когда он нужен', () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    const d = filled({ editing: true, category: 'elevator' })
    expect(stepAfter('category', d)).toBe('elevator')
    expect(stepAfter('address', d)).toBe('elevator')
    expect(stepAfter('elevator', { ...d, elevator: chosen })).toBe('review')
    expect(stepAfter('address', { ...d, elevator: chosen })).toBe('review')
    vi.unstubAllEnvs()
  })
})
