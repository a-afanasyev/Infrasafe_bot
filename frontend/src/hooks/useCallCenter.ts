import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { KANBAN_QUERY_PREFIX } from './useKanban'
import type { ApartmentNumber, CheckResult, ResidentApartment } from '../twa/pages/dispatch/api'
import type { CreateBody } from '../twa/pages/dispatch/model'

export interface CallCenterResident {
  id: number
  full_name: string
  phone: string
}

/** Тело POST /api/v2/callcenter/requests (CallCenterCreateRequest): адрес —
 *  ровно один уровень справочника (`yard_id`/`building_id`/`apartment_id`,
 *  + поля лифта); `address_text` — слова звонящего, уходят в примечания. */
export interface CallCenterBody {
  category: string
  urgency: string
  description: string
  user_id?: number
  /** Адрес — ровно один уровень справочника (двор/дом/квартира). */
  yard_id?: number
  building_id?: number | null
  apartment_id?: number
  address_text?: string
  elevator_id?: number | null
  elevator_operational?: boolean | null
}

/** Поиск жителя по строке оператора — разовый запрос по кнопке, без кэша. */
export function searchCallCenterResidents(q: string): Promise<CallCenterResident[]> {
  return apiClient.get('/api/v2/callcenter/search-resident', { params: { q } }).then(r => r.data)
}

/** Заявка от оператора колл-центра; новая карточка появляется на канбане. */
export function useCreateCallCenterRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CallCenterBody) =>
      apiClient.post('/api/v2/callcenter/requests', body).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: KANBAN_QUERY_PREFIX })
    },
  })
}

/** Вариант адреса из справочника, предложенный по словам звонящего. */
export interface AddressOption {
  type: 'yard' | 'building'
  id: number
  yard_id: number
  label: string
}

export interface AddressSuggestion {
  options: AddressOption[]
  ai_used: boolean
  category: string | null
  urgency: string | null
}

/** Возможности формы на площадке: свободный ввод адреса — только при ИИ. */
export function useCallCenterCapabilities(enabled: boolean) {
  return useQuery<{ address_suggest: boolean }>({
    queryKey: ['callcenter-capabilities'],
    queryFn: () => apiClient.get('/api/v2/callcenter/capabilities').then(r => r.data),
    enabled,
    staleTime: 5 * 60_000,
  })
}

// ── Страница диспетчера (/dispatch): те же эндпоинты, что у экрана в Telegram ──

/** Одобренные квартиры жителя — адрес в одно нажатие. */
export function callCenterResidentApartments(userId: number): Promise<ResidentApartment[]> {
  return apiClient.get(`/api/v2/callcenter/residents/${userId}/apartments`).then(r => r.data)
}

/** Номера квартир дома — узкий список без данных жильцов. */
export function useCallCenterApartments(buildingId: number | null) {
  return useQuery<ApartmentNumber[]>({
    queryKey: ['callcenter-apartments', buildingId],
    queryFn: () => apiClient.get(`/api/v2/callcenter/buildings/${buildingId}/apartments`).then(r => r.data),
    enabled: buildingId !== null,
    staleTime: 30_000,
  })
}

/** ИИ-проверка заявки перед отправкой: замечания — совет, а не запрет. */
export function checkCallCenterRequest(body: CreateBody): Promise<CheckResult> {
  return apiClient.post('/api/v2/callcenter/check', body).then(r => r.data)
}

export function createDispatchRequest(body: CreateBody): Promise<{ request_number: string }> {
  return apiClient.post('/api/v2/callcenter/requests', body).then(r => r.data)
}

/** Адрес со слов звонящего → варианты двора/дома (ИИ + поиск по справочнику). */
export function suggestCallCenterAddress(addressText: string, description: string): Promise<AddressSuggestion> {
  return apiClient
    .post('/api/v2/callcenter/address-suggest', { address_text: addressText, description: description || undefined })
    .then(r => r.data)
}
