import { apiClient } from './client'

export interface DataUrlFile {
  dataUrl: string
  /** MIME из ответа (Blob.type) — по нему решают «превью или скачать». */
  type: string
}

/**
 * Скачать файл через apiClient и отдать как data: URL.
 *
 * Site-wide CSP (infrasafe-nginx, `/uk/*`) запрещает blob: в img-src —
 * превью через `URL.createObjectURL` там молча не отрисовывается, data: URL
 * проходит. Единый хелпер для фото заявки, фото обратной связи и документов
 * жителя (раньше — три копии FileReader-обвязки по компонентам).
 */
export async function fetchFileAsDataUrl(url: string): Promise<DataUrlFile> {
  const response = await apiClient.get(url, { responseType: 'blob' })
  const blob = response.data as Blob
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => (typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('bad')))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
  return { dataUrl, type: blob.type }
}
