/**
 * Минимальные формы ответов API, используемые в TWA-страницах.
 * Заводится вместо `any` в .map/.filter над ответами twaClient.
 */
export interface TwaRequest {
  request_number: string
  status: string
  category: string
  description?: string
  requested_materials?: string
  executor_name?: string | null
  created_at: string
}

export interface TwaAnnouncement {
  id: number | string
  type?: string
  title: string
  body: string
}

export interface TwaApartment {
  apartment_id: number | string
  full_address: string
}
