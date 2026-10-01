import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { KANBAN_QUERY_PREFIX } from './useKanban'

export interface CallCenterResident {
  id: number
  full_name: string
  phone: string
}

/** Тело POST /api/v2/callcenter/requests (CallCenterCreateRequest): адрес —
 *  либо свободный `address`, либо `building_id` (+ поля лифта). */
export interface CallCenterBody {
  category: string
  urgency: string
  description: string
  user_id?: number
  address?: string
  building_id?: number | null
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
