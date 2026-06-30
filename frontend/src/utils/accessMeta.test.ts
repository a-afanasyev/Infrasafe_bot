import { describe, it, expect } from 'vitest'
import { formatAddress, formatApplicant, formatZones } from './accessMeta'
import type { ApplicantInfo, AddressInfo, ZoneRef } from '../types/access'

// t-заглушка: ключ accessControl.meta.apt → «кв. N».
const t = ((key: string, opts?: { n?: string }) =>
  key === 'accessControl.meta.apt' ? `кв. ${opts?.n}` : key) as never

describe('formatAddress', () => {
  it('собирает двор · дом · кв.', () => {
    const a: AddressInfo = {
      apartment_id: 55,
      apartment_number: '12',
      entrance: null,
      floor: null,
      building_id: 5,
      building_address: 'ул. Тест 1',
      yard_id: 1,
      yard_name: 'Двор 1',
    }
    expect(formatAddress(a, t)).toBe('Двор 1 · ул. Тест 1 · кв. 12')
  })

  it('фолбэк на #id если нет частей', () => {
    const a: AddressInfo = {
      apartment_id: 7,
      apartment_number: null,
      entrance: null,
      floor: null,
      building_id: null,
      building_address: null,
      yard_id: null,
      yard_name: null,
    }
    expect(formatAddress(a, t)).toBe('#7')
  })

  it('null → тире', () => {
    expect(formatAddress(null, t)).toBe('—')
  })
})

describe('formatApplicant', () => {
  it('имя + телефон + username', () => {
    const a: ApplicantInfo = {
      user_id: 4,
      name: 'Андрей',
      phone: '+998901112233',
      username: 'andrey',
      telegram_id: 1,
    }
    expect(formatApplicant(a)).toBe('Андрей · +998901112233 · @andrey')
  })

  it('фолбэк на ID без имени', () => {
    const a: ApplicantInfo = {
      user_id: 9,
      name: null,
      phone: null,
      username: null,
      telegram_id: null,
    }
    expect(formatApplicant(a)).toBe('ID 9')
  })

  it('null → тире', () => {
    expect(formatApplicant(null)).toBe('—')
  })
})

describe('formatZones', () => {
  it('имена через запятую', () => {
    const zones: ZoneRef[] = [
      { id: 1, code: 'A', name: 'Паркинг А' },
      { id: 2, code: 'B', name: null },
    ]
    expect(formatZones(zones)).toBe('Паркинг А, B')
  })

  it('пусто → тире', () => {
    expect(formatZones([])).toBe('—')
    expect(formatZones(null)).toBe('—')
  })
})
