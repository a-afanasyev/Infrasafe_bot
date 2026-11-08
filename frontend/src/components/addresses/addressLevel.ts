/**
 * Значение выбора адреса заявки из справочника (`AddressLevelPicker`):
 * двор → дом → квартира. Уровень заявки — самый глубокий выбранный.
 * Решение владельца 2026-11-07: свободный текст адреса не принимается.
 */
export interface AddressLevelValue {
  yardId: number | null
  buildingId: number | null
  apartmentId: number | null
}

export const EMPTY_ADDRESS_LEVEL: AddressLevelValue = { yardId: null, buildingId: null, apartmentId: null }

export type AddressLevelBody = { yard_id: number } | { building_id: number } | { apartment_id: number }

/** Тело для API — ровно один уровень; null, пока двор не выбран. */
export function addressLevelBody(v: AddressLevelValue): AddressLevelBody | null {
  if (v.apartmentId !== null) return { apartment_id: v.apartmentId }
  if (v.buildingId !== null) return { building_id: v.buildingId }
  if (v.yardId !== null) return { yard_id: v.yardId }
  return null
}
