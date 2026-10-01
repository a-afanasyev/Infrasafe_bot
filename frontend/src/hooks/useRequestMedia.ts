import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { fetchFileAsDataUrl } from '../api/fileDataUrl'

export interface MediaItem {
  id: number
  file_type: string
  mime_type: string
  category?: string | null
}

/** Список медиа заявки; загрузка (`useRequestMediaUpload`) инвалидирует этот ключ. */
export function requestMediaQueryKey(requestNumber: string) {
  return ['request-media', requestNumber] as const
}

/** data:-URL файла по id — общий для превью и лайтбокса (FE-11). */
export function mediaBlobQueryKey(mediaId: number) {
  return ['media-blob', mediaId] as const
}

export function useRequestMediaList(requestNumber: string) {
  return useQuery<MediaItem[]>({
    queryKey: requestMediaQueryKey(requestNumber),
    queryFn: () => apiClient.get(`/api/v2/media/request/${requestNumber}`).then(r => r.data),
    enabled: !!requestNumber,
    staleTime: 60_000,
  })
}

/** Байты медиа заявки как data: URL — один кэш на превью и лайтбокс. */
export function useMediaBlob(mediaId: number) {
  return useQuery({
    queryKey: mediaBlobQueryKey(mediaId),
    queryFn: () => fetchFileAsDataUrl(`/api/v2/media/${mediaId}/file`).then(f => f.dataUrl),
    staleTime: 5 * 60_000,
    // WR-08: base64 data-URLs are heavy; with the default 5-min gcTime they
    // linger in cache long after the modal closes. Drop them ~30s after the
    // last observer (thumb or lightbox) unmounts to free memory promptly.
    gcTime: 30_000,
    retry: false,
  })
}
