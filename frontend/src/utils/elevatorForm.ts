import { emptyToNull, toIntOrNull } from './elevatorsFormat'
import type { ElevatorCreateIn, ElevatorDetail, ElevatorPatchIn } from '../types/elevators'

/**
 * Чистая модель формы лифта (строки инпутов ↔ payload API). Без React —
 * тестируется напрямую; страница/поля только читают и патчат `ElevatorFormState`.
 */

export interface ElevatorFormState {
  yard_id: string
  building_id: string
  entrance_number: string
  elevator_number: string
  passport_number: string
  manufacturer: string
  serial_number: string
  factory_number: string
  model: string
  production_year: string
  capacity_kg: string
  floors_served: string
  service_org_name: string
  service_org_phone: string
  contract_number: string
  contract_until: string
  cert_number: string
  cert_valid_until: string
  cert_act_url: string
  downtime_reason: string
  spare_part_expected_on: string
  publish_downtime_details: boolean
  is_public: boolean
}

export type ElevatorFormTextKey = Exclude<keyof ElevatorFormState, 'publish_downtime_details' | 'is_public'>

export const EMPTY_ELEVATOR_FORM: ElevatorFormState = {
  yard_id: '',
  building_id: '',
  entrance_number: '',
  elevator_number: '',
  passport_number: '',
  manufacturer: '',
  serial_number: '',
  factory_number: '',
  model: '',
  production_year: '',
  capacity_kg: '',
  floors_served: '',
  service_org_name: '',
  service_org_phone: '',
  contract_number: '',
  contract_until: '',
  cert_number: '',
  cert_valid_until: '',
  cert_act_url: '',
  downtime_reason: '',
  spare_part_expected_on: '',
  publish_downtime_details: false,
  is_public: true,
}

const str = (v: string | number | null | undefined): string => (v === null || v === undefined ? '' : String(v))

/** Карточка → форма (режим редактирования). */
export function formFromDetail(d: ElevatorDetail): ElevatorFormState {
  return {
    yard_id: str(d.yard_id),
    building_id: str(d.building_id),
    entrance_number: str(d.entrance_number),
    elevator_number: str(d.elevator_number),
    passport_number: d.passport_number,
    manufacturer: d.manufacturer,
    serial_number: d.serial_number,
    factory_number: str(d.factory_number),
    model: str(d.model),
    production_year: str(d.production_year),
    capacity_kg: str(d.capacity_kg),
    floors_served: str(d.floors_served),
    service_org_name: str(d.service_org_name),
    service_org_phone: str(d.service_org_phone),
    contract_number: str(d.contract_number),
    contract_until: str(d.contract_until),
    cert_number: str(d.cert_number),
    cert_valid_until: str(d.cert_valid_until),
    cert_act_url: str(d.cert_act_url),
    downtime_reason: str(d.downtime_reason),
    spare_part_expected_on: str(d.spare_part_expected_on),
    publish_downtime_details: d.publish_downtime_details,
    is_public: d.is_public,
  }
}

/**
 * «Скопировать предыдущий» (Р13): паспортные/договорные поля из другого лифта,
 * КРОМЕ номера лифта, серийника, номера паспорта и подъезда — их вводит оператор.
 * Адрес (двор/дом) тоже берём — обычно лифты заводят по одному дому.
 */
export function copyPassportFrom(current: ElevatorFormState, source: ElevatorDetail): ElevatorFormState {
  const copied = formFromDetail(source)
  return {
    ...copied,
    entrance_number: current.entrance_number,
    elevator_number: current.elevator_number,
    passport_number: current.passport_number,
    serial_number: current.serial_number,
    downtime_reason: current.downtime_reason,
    spare_part_expected_on: current.spare_part_expected_on,
  }
}

export type ElevatorFormError = 'required' | 'positiveInt'

/** Клиентская валидация обязательных полей; null = ок. */
export function validateElevatorForm(f: ElevatorFormState): ElevatorFormError | null {
  const requiredFilled =
    f.building_id !== '' &&
    f.entrance_number.trim() !== '' &&
    f.elevator_number.trim() !== '' &&
    f.passport_number.trim() !== '' &&
    f.manufacturer.trim() !== '' &&
    f.serial_number.trim() !== ''
  if (!requiredFilled) return 'required'
  const entrance = toIntOrNull(f.entrance_number)
  const number = toIntOrNull(f.elevator_number)
  if (entrance === null || entrance <= 0 || number === null || number <= 0) return 'positiveInt'
  return null
}

function optionalPayload(f: ElevatorFormState) {
  return {
    factory_number: emptyToNull(f.factory_number),
    model: emptyToNull(f.model),
    production_year: toIntOrNull(f.production_year),
    capacity_kg: toIntOrNull(f.capacity_kg),
    floors_served: emptyToNull(f.floors_served),
    service_org_name: emptyToNull(f.service_org_name),
    service_org_phone: emptyToNull(f.service_org_phone),
    contract_number: emptyToNull(f.contract_number),
    contract_until: emptyToNull(f.contract_until),
    cert_number: emptyToNull(f.cert_number),
    cert_valid_until: emptyToNull(f.cert_valid_until),
    cert_act_url: emptyToNull(f.cert_act_url),
    downtime_reason: emptyToNull(f.downtime_reason),
    spare_part_expected_on: emptyToNull(f.spare_part_expected_on),
    publish_downtime_details: f.publish_downtime_details,
    is_public: f.is_public,
  }
}

/** Форма → ElevatorCreateIn (вызывать после validateElevatorForm === null). */
export function toCreatePayload(f: ElevatorFormState): ElevatorCreateIn {
  return {
    ...optionalPayload(f),
    building_id: Number(f.building_id),
    entrance_number: Number(f.entrance_number),
    elevator_number: Number(f.elevator_number),
    passport_number: f.passport_number.trim(),
    manufacturer: f.manufacturer.trim(),
    serial_number: f.serial_number.trim(),
  }
}

/** Форма → ElevatorPatchIn с оптимистичной блокировкой по версии карточки. */
export function toPatchPayload(f: ElevatorFormState, expectedVersion: number): ElevatorPatchIn {
  return { ...toCreatePayload(f), expected_version: expectedVersion }
}
