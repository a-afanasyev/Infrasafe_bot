/**
 * Значение полей «Лифт» формы колл-центра (дом → лифт → «работает?»).
 * Вынесено из компонента: react-refresh требует, чтобы файл компонента
 * экспортировал только компоненты.
 */
export interface CallCenterElevatorValue {
  buildingId: number | null
  elevatorId: number | null
  operational: boolean | null
}

export const EMPTY_ELEVATOR_VALUE: CallCenterElevatorValue = {
  buildingId: null,
  elevatorId: null,
  operational: null,
}

/** Все три поля обязательны — иначе сервер ответит 422 (Р11). */
export function isElevatorValueComplete(v: CallCenterElevatorValue): boolean {
  return v.buildingId !== null && v.elevatorId !== null && v.operational !== null
}
