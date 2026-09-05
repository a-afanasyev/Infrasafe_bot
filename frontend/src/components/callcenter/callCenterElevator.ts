/**
 * Значение полей «Лифт» формы колл-центра (двор → дом → лифт → «работает?»).
 * Двор — только для каскада справочника (в тело запроса не уходит).
 * Вынесено из компонента: react-refresh требует, чтобы файл компонента
 * экспортировал только компоненты.
 */
export interface CallCenterElevatorValue {
  yardId: number | null
  buildingId: number | null
  elevatorId: number | null
  operational: boolean | null
}

export const EMPTY_ELEVATOR_VALUE: CallCenterElevatorValue = {
  yardId: null,
  buildingId: null,
  elevatorId: null,
  operational: null,
}

/** Дом, лифт и «работает?» обязательны — иначе сервер ответит 422 (Р11). */
export function isElevatorValueComplete(v: CallCenterElevatorValue): boolean {
  return v.buildingId !== null && v.elevatorId !== null && v.operational !== null
}
