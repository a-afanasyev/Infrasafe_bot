/**
 * Телефон диспетчерской для TWA (Р18: в отказе по лифту в работах даём куда
 * звонить). Источник — тот же board_config, что у бота: `/api/v2/announcements`
 * отдаёт `emergency_phones = [contacts.dispatch_phone]` (см.
 * `api/routes/announcements.py`). Отдельного эндпоинта под один телефон нет.
 *
 * Запрос включается только когда телефон реально нужен (`enabled`), чтобы
 * штатный путь мастера не делал лишнего вызова.
 */
import { useQuery } from '@tanstack/react-query'
import { twaClient } from '../twaClient'
import { useApiLang } from '../../utils/apiLang'

interface AnnouncementsOut {
  emergency_phones?: (string | null)[]
}

export function useDispatchPhone(enabled: boolean): string | null {
  const lang = useApiLang()
  const query = useQuery<AnnouncementsOut>({
    queryKey: ['twa', 'announcements', lang],
    queryFn: () => twaClient.get('/api/v2/announcements', { params: { lang } }).then((r) => r.data),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
  const phone = query.data?.emergency_phones?.[0]
  return typeof phone === 'string' && phone.trim() ? phone.trim() : null
}
