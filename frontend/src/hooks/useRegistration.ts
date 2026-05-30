import axios from 'axios'
import { useTelegramSDK } from '../twa/hooks/useTelegramSDK'

// Shares the SPA base path (/uk/) — request URLs become /uk/api/...
const BASE_URL =
  import.meta.env.VITE_API_URL ??
  import.meta.env.BASE_URL.replace(/\/$/, '')

const http = axios.create({ baseURL: BASE_URL })

export interface RegistrationApartment {
  id: number
  yard_name?: string
  building_address?: string
  apartment_number: string
}

export interface RegistrationStart {
  registration_ticket: string
  prefill: { first_name?: string; last_name?: string; phone?: string }
  apartments: RegistrationApartment[]
}

export interface RegistrationSubmitPayload {
  full_name: string
  phone: string
  apartment_id: number
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
    const { data } = await http.post('/api/v2/registration/applicant', payload, {
      headers: { Authorization: `Bearer ${ticket}` },
    })
    return data as { status: string }
  }

  return { initData, start, submit }
}
