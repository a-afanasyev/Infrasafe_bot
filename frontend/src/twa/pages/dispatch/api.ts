/** Запросы экрана диспетчера: справочник адресов и колл-центр. */
import { twaClient } from '../../twaClient'
import type { CreateBody } from './model'

export interface ResidentMatch {
  id: number
  full_name: string | null
  phone: string | null
}

export interface ResidentApartment {
  id: number
  label: string
  building_id: number
}

export interface Yard {
  id: number
  name: string
}

export interface Building {
  id: number
  address: string
}

export interface ApartmentNumber {
  id: number
  number: string
}

export interface AddressOption {
  type: 'yard' | 'building'
  id: number
  yard_id: number
  label: string
}

export interface CheckIssue {
  field: 'description' | 'category' | 'urgency' | 'address'
  code: string
  suggestion: string | null
  options: AddressOption[]
}

export interface CheckResult {
  ai_used: boolean
  issues: CheckIssue[]
}

const CC = '/api/v2/callcenter'
const get = <T,>(url: string, params?: Record<string, string>): Promise<T> =>
  twaClient.get(url, params ? { params } : undefined).then((r) => r.data)

export const searchResidents = (q: string) => get<ResidentMatch[]>(`${CC}/search-resident`, { q })
export const residentApartments = (userId: number) => get<ResidentApartment[]>(`${CC}/residents/${userId}/apartments`)
export const listYards = () => get<Yard[]>('/api/v2/addresses/yards')
export const listBuildings = (yardId: number) => get<Building[]>(`/api/v2/addresses/yards/${yardId}/buildings`)
export const listApartments = (buildingId: number) => get<ApartmentNumber[]>(`${CC}/buildings/${buildingId}/apartments`)
/** Проверка ИИ доступна на площадке? (тот же флаг, что у подсказки адреса) */
export const aiCheckEnabled = () =>
  get<{ address_suggest: boolean }>(`${CC}/capabilities`).then((c) => c.address_suggest)

export const checkRequest = (body: CreateBody): Promise<CheckResult> =>
  twaClient.post(`${CC}/check`, body).then((r) => r.data)
export const createRequest = (body: CreateBody): Promise<{ request_number: string }> =>
  twaClient.post(`${CC}/requests`, body).then((r) => r.data)
