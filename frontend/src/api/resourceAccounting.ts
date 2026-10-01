import { apiClient } from './client'

/**
 * Минтинг одноразового тикета для тихого входа в модуль «Учёт ресурсов»:
 * наш backend маппит роль УК→ресурс, модуль обменивает тикет на свою сессию.
 */
export async function mintResourceTicket(): Promise<string> {
  return (await apiClient.post('/api/v2/resource-accounting/ticket')).data.ticket
}
