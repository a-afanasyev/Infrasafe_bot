import { useQuery } from '@tanstack/react-query'
import { twaClient } from '../../twaClient'
import type { ApartmentOption } from './types'

/**
 * Подтверждённые (approved) квартиры жителя.
 *
 * Бэкенд контроля доступа привязывает заявку/пропуск к `apartment_id` из
 * approved-квартир пользователя. Тот же список отдаёт профиль TWA
 * (`/api/v2/profile/apartments` → `{ apartment_id, full_address }`), который
 * уже используется на ProfilePage, поэтому переиспользуем его, а не вводим
 * отдельный access-эндпоинт.
 */
export function useApartments() {
  return useQuery<ApartmentOption[]>({
    queryKey: ['twa', 'my-apartments'],
    queryFn: () => twaClient.get('/api/v2/profile/apartments').then((r) => r.data),
    staleTime: 60_000,
  })
}
