import { apiClient } from '../api/client'

/**
 * Скачать CSV/файл с API: fetch через apiClient (cookie-auth и refresh
 * сохраняются) → blob → клик по временной ссылке.
 */
export async function downloadCsv(url: string, params: Record<string, unknown>, filename: string) {
  const resp = await apiClient.get(url, { params, responseType: 'blob' })
  const href = URL.createObjectURL(resp.data as Blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
  URL.revokeObjectURL(href)
}
