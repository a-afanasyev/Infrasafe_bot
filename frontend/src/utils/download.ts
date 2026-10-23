import { apiClient } from '../api/client'

/**
 * Скачать CSV/файл с API: fetch через apiClient (cookie-auth и refresh
 * сохраняются) → blob → клик по временной ссылке.
 */
export async function downloadCsv(url: string, params: Record<string, unknown>, filename: string) {
  const resp = await apiClient.get(url, { params, responseType: 'blob' })
  saveBlob(resp.data as Blob, filename)
}

/** То же для POST-выгрузок с телом запроса (отчёт с логотипом и выбором листов). */
export async function downloadPost(url: string, params: Record<string, unknown>, body: unknown, filename: string) {
  const resp = await apiClient.post(url, body, { params, responseType: 'blob' })
  saveBlob(resp.data as Blob, filename)
}

function saveBlob(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
  URL.revokeObjectURL(href)
}
