/**
 * Выбор лифта в мастере создания заявки TWA (шаг «Лифт»): значение, пустой
 * дефолт, проверка полноты и разрешение дома по выбранному адресу. Вынесено
 * из компонента ElevatorStep — react-refresh требует «только компоненты».
 */
import type { ElevatorStatus } from '../../types/elevators'

export interface ElevatorSelection {
  elevatorId: number | null
  elevatorLabel: string
  elevatorStatus: ElevatorStatus | null
  operational: boolean | null
}

export const EMPTY_ELEVATOR_SELECTION: ElevatorSelection = {
  elevatorId: null,
  elevatorLabel: '',
  elevatorStatus: null,
  operational: null,
}

export function isElevatorSelectionComplete(v: ElevatorSelection): boolean {
  return v.elevatorId !== null && v.operational !== null
}

/** Дом для запроса лифтов: квартира → её building_id, дом → сам id, двор → нет. */
export function resolveBuildingId(
  addressType: 'yard' | 'building' | 'apartment' | null,
  addressId: number | null,
  apartments: ReadonlyArray<{ id: number; building_id?: number }>,
): number | null {
  if (addressId === null) return null
  if (addressType === 'building') return addressId
  if (addressType === 'apartment') return apartments.find((a) => a.id === addressId)?.building_id ?? null
  return null
}
