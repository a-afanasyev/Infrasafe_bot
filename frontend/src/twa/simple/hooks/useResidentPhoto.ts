import { useQuery } from '@tanstack/react-query'
import { twaClient } from '../../twaClient'

interface MediaItem {
  id: number
  file_type?: string
  mime_type?: string
  category?: string | null
}

function isResidentPhoto(m: MediaItem): boolean {
  if (m.category === 'completion_photo') return false
  return m.file_type === 'photo' || !!m.mime_type?.startsWith('image/')
}

/**
 * id первого фото жителя заявки. Ключ и запрос — как у MediaGallery
 * (['twa','media',n]), кэш общий. `known` — id уже известен (плитка пула:
 * число или null «фото нет»), тогда запроса нет.
 */
export function useResidentPhotoId(requestNumber: string | undefined, known?: number | null): number | null {
  const { data } = useQuery<MediaItem[]>({
    queryKey: ['twa', 'media', requestNumber],
    queryFn: () => twaClient.get(`/api/v2/media/request/${requestNumber}`).then((r) => r.data),
    enabled: !!requestNumber && known === undefined,
    staleTime: 60_000,
  })
  if (known !== undefined) return known ?? null
  return (Array.isArray(data) ? data : []).find(isResidentPhoto)?.id ?? null
}

// CSP /uk/* запрещает blob: в img-src — байты превращаем в data: URL
// (как MediaGallery и превью PhotoUploader).
export function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () =>
      typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('FileReader: not a string'))
    reader.onerror = () => reject(reader.error ?? new Error('FileReader error'))
    reader.readAsDataURL(blob)
  })
}
