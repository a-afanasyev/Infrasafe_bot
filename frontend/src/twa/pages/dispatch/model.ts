/**
 * Модель экрана диспетчера (приём заявки по телефону): черновик, порядок
 * шагов и тела запросов. Чистые функции — без React и сети.
 */
import { isElevatorsEnabled } from '../../../utils/featureFlags'
import {
  EMPTY_ELEVATOR_SELECTION,
  isElevatorSelectionComplete,
  type ElevatorSelection,
} from '../../components/elevatorSelection'
import type { AddressOption, CheckIssue, ResidentApartment } from './api'

export type Step = 'phone' | 'address' | 'category' | 'elevator' | 'description' | 'urgency' | 'review'
export type AddressLevel = 'yard' | 'building' | 'apartment'

/** Адрес заявки — ровно один уровень справочника. */
export interface Address {
  level: AddressLevel
  id: number
  label: string
  /** Дом адреса (для лифтов); у двора — null. */
  buildingId: number | null
}

export interface Resident {
  id: number
  fullName: string
}

export interface Draft {
  step: Step
  /** Шаг открыт из сводки: после ответа возвращаемся в сводку. */
  editing: boolean
  phone: string
  callerName: string
  resident: Resident | null
  residentApartments: ResidentApartment[]
  address: Address | null
  category: string
  elevator: ElevatorSelection
  description: string
  urgency: string
}

export const EMPTY_DRAFT: Draft = {
  step: 'phone',
  editing: false,
  phone: '',
  callerName: '',
  resident: null,
  residentApartments: [],
  address: null,
  category: '',
  elevator: EMPTY_ELEVATOR_SELECTION,
  description: '',
  urgency: '',
}

const PHONE_MIN_DIGITS = 9

export const phoneDigits = (raw: string): string => raw.replace(/\D/g, '')
export const isPhoneComplete = (raw: string): boolean => phoneDigits(raw).length >= PHONE_MIN_DIGITS
/** Жителя ищем по последним 9 цифрам: код страны пишут по-разному. */
export const residentQuery = (raw: string): string => phoneDigits(raw).slice(-PHONE_MIN_DIGITS)

export const needsElevator = (d: Pick<Draft, 'category'>): boolean =>
  d.category === 'elevator' && isElevatorsEnabled()

function order(d: Draft): Step[] {
  return ['phone', 'address', 'category', ...(needsElevator(d) ? (['elevator'] as Step[]) : []), 'description', 'urgency', 'review']
}

/** Категория «Лифт», а лифт не выбран (или сброшен сменой адреса). */
export const elevatorMissing = (d: Draft): boolean =>
  needsElevator(d) && !isElevatorSelectionComplete(d.elevator)

/** Новый адрес: лифт другого дома к нему не относится — выбор сбрасывается. */
export function withAddress(d: Draft, address: Address): Pick<Draft, 'address' | 'elevator'> {
  const sameBuilding = d.address?.buildingId === address.buildingId
  return { address, elevator: sameBuilding ? d.elevator : EMPTY_ELEVATOR_SELECTION }
}

export function stepAfter(step: Step, d: Draft): Step {
  // Правка из сводки возвращает в сводку — но не мимо выбора лифта, если он
  // стал нужен (категория «Лифт») или сброшен (другой адрес).
  if (d.editing) return step !== 'elevator' && elevatorMissing(d) ? 'elevator' : 'review'
  const steps = order(d)
  return steps[Math.min(steps.indexOf(step) + 1, steps.length - 1)]
}

export function stepBefore(step: Step, d: Draft): Step {
  if (d.editing) return 'review'
  const steps = order(d)
  return steps[Math.max(steps.indexOf(step) - 1, 0)]
}

/** Житель становится автором заявки, кроме случая чужой квартиры (сервер даст 422). */
function linkedResidentId(d: Draft): number | undefined {
  if (!d.resident || !d.address) return undefined
  const foreignApartment =
    d.address.level === 'apartment' && !d.residentApartments.some((a) => a.id === d.address?.id)
  return foreignApartment ? undefined : d.resident.id
}

function addressBody(address: Address | null): Record<string, number> {
  return address ? { [`${address.level}_id`]: address.id } : {}
}

export interface CreateBody {
  category: string
  urgency: string
  description: string
  yard_id?: number
  building_id?: number
  apartment_id?: number
  user_id?: number
  caller_name?: string
  caller_phone?: string
  acceptance_mode?: 'manager'
  elevator_id?: number
  elevator_operational?: boolean
}

export function buildCheckBody(d: Draft): CreateBody {
  return { category: d.category, urgency: d.urgency, description: d.description.trim(), ...addressBody(d.address) }
}

export function buildCreateBody(d: Draft): CreateBody {
  const body: CreateBody = buildCheckBody(d)
  const userId = linkedResidentId(d)
  if (userId !== undefined) {
    body.user_id = userId
  } else {
    // Автор — диспетчер: звонящий уходит в примечания, а принимает работу
    // менеджер (у диспетчера экрана приёмки нет).
    const name = (d.resident?.fullName ?? d.callerName).trim()
    if (name) body.caller_name = name
    // «+» — только если его ввели: номер без кода страны не выдаём за международный.
    body.caller_phone = `${d.phone.trim().startsWith('+') ? '+' : ''}${phoneDigits(d.phone)}`
    body.acceptance_mode = 'manager'
  }
  if (needsElevator(d) && d.elevator.elevatorId !== null && d.elevator.operational !== null) {
    body.elevator_id = d.elevator.elevatorId
    body.elevator_operational = d.elevator.operational
  }
  return body
}

/** «Исправить»: подставить предложенное значение замечания. */
export function applyIssueFix(d: Draft, issue: CheckIssue, option?: AddressOption): Draft {
  if (issue.field === 'category' && issue.suggestion) return { ...d, category: issue.suggestion }
  if (issue.field === 'urgency' && issue.suggestion) return { ...d, urgency: issue.suggestion }
  if (issue.field === 'address' && option) {
    return {
      ...d,
      ...withAddress(d, {
        level: option.type,
        id: option.id,
        label: option.label,
        buildingId: option.type === 'building' ? option.id : null,
      }),
    }
  }
  return d
}
