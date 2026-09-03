import axios from 'axios'
import { useTelegramSDK } from '../twa/hooks/useTelegramSDK'

// Shares the SPA base path (/uk/) — request URLs become /uk/api/...
const BASE_URL =
  import.meta.env.VITE_API_URL ??
  import.meta.env.BASE_URL.replace(/\/$/, '')

const http = axios.create({ baseURL: BASE_URL })

export interface RegistrationYard {
  id: number
  name: string
}

export interface RegistrationBuilding {
  id: number
  address: string
}

export interface RegistrationApartment {
  id: number
  apartment_number: string
  floor?: number | null
  entrance?: number | null
}

export interface RegistrationStart {
  registration_ticket: string
  prefill: { first_name?: string; last_name?: string; phone?: string | null }
}

/** Телефон в теле не передаётся: сервер берёт users.phone, который бот
 * сохранил из Telegram-контакта (спека 2026-09-03 §4.4). */
export interface RegistrationSubmitPayload {
  full_name: string
  apartment_id: number
}

export interface RegistrationContactStatus {
  phone: string | null
}

function bearer(ticket: string) {
  return { headers: { Authorization: `Bearer ${ticket}` } }
}

export function useRegistration() {
  // useTelegramSDK returns an object exposing `.initData` (string, '' until SDK ready).
  const { initData } = useTelegramSDK()

  async function start(): Promise<RegistrationStart> {
    const { data } = await http.post('/api/v2/registration/start', { init_data: initData })
    return data as RegistrationStart
  }

  async function submit(
    ticket: string,
    payload: RegistrationSubmitPayload
  ): Promise<{ status: string }> {
    const { data } = await http.post('/api/v2/registration/applicant', payload, bearer(ticket))
    return data as { status: string }
  }

  async function yards(ticket: string): Promise<RegistrationYard[]> {
    const { data } = await http.get('/api/v2/registration/yards', bearer(ticket))
    return data as RegistrationYard[]
  }

  async function buildings(ticket: string, yardId: number): Promise<RegistrationBuilding[]> {
    const { data } = await http.get(`/api/v2/registration/yards/${yardId}/buildings`, bearer(ticket))
    return data as RegistrationBuilding[]
  }

  async function apartments(ticket: string, buildingId: number): Promise<RegistrationApartment[]> {
    const { data } = await http.get(
      `/api/v2/registration/buildings/${buildingId}/apartments`,
      bearer(ticket)
    )
    return data as RegistrationApartment[]
  }

  async function contactStatus(ticket: string): Promise<RegistrationContactStatus> {
    const { data } = await http.get('/api/v2/registration/contact-status', bearer(ticket))
    return data as RegistrationContactStatus
  }

  return { initData, start, submit, yards, buildings, apartments, contactStatus }
}
