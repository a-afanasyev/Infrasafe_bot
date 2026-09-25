import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { twaClient } from '../../twaClient'
import { blobToDataUrl } from '../hooks/useResidentPhoto'
import { limitMedia } from '../hooks/useLazyMedia'

interface Props {
  mediaId: number
  alt: string
  className: string
  /** Что показать, пока фото грузится или если не загрузилось. */
  fallback: ReactNode
  /** false — не грузить (плитка вне экрана). */
  enabled?: boolean
}

/** Фото из медиа-сервиса: байты с Bearer-токеном → data: URL (кэш навсегда). */
export function AuthPhoto({ mediaId, alt, className, fallback, enabled = true }: Props) {
  const { data: url } = useQuery<string>({
    queryKey: ['twa', 'simple', 'media-file', mediaId],
    queryFn: () =>
      limitMedia(() =>
        twaClient
          .get(`/api/v2/media/${mediaId}/file`, { responseType: 'blob' })
          .then((r) => blobToDataUrl(r.data as Blob)),
      ),
    staleTime: Infinity,
    enabled,
  })
  if (!url) return <>{fallback}</>
  return <img src={url} alt={alt} className={className} />
}
