import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../twaClient'
import { X } from 'lucide-react'

interface MediaItem {
  id: number
  file_type: string
  mime_type: string
  caption?: string | null
}

interface Props {
  requestNumber: string
}

/**
 * TWA-15: gallery for media files attached to a request.
 *
 * Loads metadata via /api/v2/media/request/{number}, then per-item fetches
 * binary bytes via /api/v2/media/{id}/file as a blob (we can't put a
 * Bearer token on a plain <img src=>). Tap a thumb → fullscreen lightbox.
 */
export default function MediaGallery({ requestNumber }: Props) {
  const { t } = useTranslation()
  const [lightboxId, setLightboxId] = useState<number | null>(null)

  const { data: items = [], isLoading } = useQuery<MediaItem[]>({
    queryKey: ['media', requestNumber],
    queryFn: () =>
      twaClient
        .get(`/api/v2/media/request/${requestNumber}`)
        .then((r) => r.data),
    enabled: !!requestNumber,
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div className="text-[12px] text-gray-400">{t('common.loading')}</div>
    )
  }

  if (items.length === 0) {
    return null
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {items.map((m) => (
          <MediaThumb
            key={m.id}
            id={m.id}
            isVideo={m.file_type === 'video'}
            onOpen={() => setLightboxId(m.id)}
          />
        ))}
      </div>
      {lightboxId !== null && (
        <Lightbox
          id={lightboxId}
          onClose={() => setLightboxId(null)}
        />
      )}
    </div>
  )
}

interface ThumbProps {
  id: number
  isVideo: boolean
  onOpen: () => void
}

function MediaThumb({ id, isVideo, onOpen }: ThumbProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [errored, setErrored] = useState(false)

  useEffect(() => {
    let cancelled = false
    let blobUrl: string | null = null
    twaClient
      .get(`/api/v2/media/${id}/file`, { responseType: 'blob' })
      .then((r) => {
        if (cancelled) return
        blobUrl = URL.createObjectURL(r.data as Blob)
        setUrl(blobUrl)
      })
      .catch(() => {
        if (!cancelled) setErrored(true)
      })
    return () => {
      cancelled = true
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
  }, [id])

  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={!url || errored}
      className="relative w-20 h-20 rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 active:scale-95 transition-transform"
    >
      {url && (
        <img
          src={url}
          alt=""
          className="w-full h-full object-cover"
        />
      )}
      {isVideo && (
        <span className="absolute bottom-1 right-1 bg-black/70 text-white text-[10px] px-1 rounded">▶</span>
      )}
    </button>
  )
}

interface LightboxProps {
  id: number
  onClose: () => void
}

function Lightbox({ id, onClose }: LightboxProps) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let blobUrl: string | null = null
    twaClient
      .get(`/api/v2/media/${id}/file`, { responseType: 'blob' })
      .then((r) => {
        if (cancelled) return
        blobUrl = URL.createObjectURL(r.data as Blob)
        setUrl(blobUrl)
      })
      .catch(() => {})
    return () => {
      cancelled = true
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
  }, [id])

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 text-white flex items-center justify-center"
      >
        <X size={20} />
      </button>
      {url ? (
        <img
          src={url}
          alt=""
          className="max-w-full max-h-full object-contain"
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <div className="text-white text-[14px]">…</div>
      )}
    </div>
  )
}
