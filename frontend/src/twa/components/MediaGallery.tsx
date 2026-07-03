import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../twaClient'
import { X, ImageOff } from 'lucide-react'

interface MediaItem {
  id: number
  file_type: string
  mime_type: string
  caption?: string | null
  category?: string | null
}

interface Props {
  requestNumber: string
  /**
   * Which media to show. 'request' = everything except the completion report;
   * 'completion' = only the executor's completion_photo report. Omit to show
   * all. Lets a detail page render two distinct sections (Фото / Фотоотчёт).
   */
  kind?: 'request' | 'completion'
  /** Optional section title; when set, the gallery renders its own card and
   *  hides entirely (title included) when it has no matching media. */
  title?: string
  /**
   * TWA-20: lets the host page intercept the Telegram BackButton. When the
   * lightbox opens we hand the parent a `close` callback; when it closes we
   * hand `null`. The page's BackButton handler calls `close()` first if set,
   * so back closes the lightbox instead of navigating away from the page.
   */
  onLightboxChange?: (close: (() => void) | null) => void
}

/**
 * TWA-15: gallery for media files attached to a request.
 *
 * Loads metadata via /api/v2/media/request/{number}, then per-item fetches
 * binary bytes via /api/v2/media/{id}/file as a blob (we can't put a
 * Bearer token on a plain <img src=>). Tap a thumb → fullscreen lightbox.
 */
export default function MediaGallery({ requestNumber, kind, title, onLightboxChange }: Props) {
  const { t } = useTranslation()
  const [lightboxId, setLightboxId] = useState<number | null>(null)

  const { data: items = [], isLoading } = useQuery<MediaItem[]>({
    queryKey: ['twa', 'media', requestNumber],
    queryFn: () =>
      twaClient
        .get(`/api/v2/media/request/${requestNumber}`)
        .then((r) => r.data),
    enabled: !!requestNumber,
    staleTime: 60_000,
  })

  // TWA-20: publish open/close state to the host page so it can route the
  // Telegram BackButton to closing the lightbox.
  useEffect(() => {
    if (!onLightboxChange) return
    onLightboxChange(lightboxId !== null ? () => setLightboxId(null) : null)
    return () => onLightboxChange(null)
  }, [lightboxId, onLightboxChange])

  const visible = items.filter((m) => {
    if (kind === 'completion') return m.category === 'completion_photo'
    if (kind === 'request') return m.category !== 'completion_photo'
    return true
  })

  // While loading we render nothing (title included) to avoid an empty card
  // flash; same once we know there's no matching media.
  if (isLoading || visible.length === 0) {
    return title ? null : isLoading ? <div className="text-[12px] text-gray-400">{t('common.loading')}</div> : null
  }

  const grid = (
    <div className="flex flex-wrap gap-2">
      {visible.map((m) => (
        <MediaThumb
          key={m.id}
          id={m.id}
          isVideo={m.file_type === 'video'}
          onOpen={() => setLightboxId(m.id)}
        />
      ))}
    </div>
  )

  const lightbox = lightboxId !== null && (
    // TWA-30: key by id so React remounts on thumbnail switch — a fresh
    // component can't show the data-URL from a previous, slower fetch.
    <Lightbox key={lightboxId} id={lightboxId} onClose={() => setLightboxId(null)} />
  )

  if (title) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
        <h3 className="font-semibold text-[13px] text-gray-900 dark:text-gray-100 mb-2">{title}</h3>
        {grid}
        {lightbox}
      </div>
    )
  }

  return (
    <div>
      {grid}
      {lightbox}
    </div>
  )
}

interface ThumbProps {
  id: number
  isVideo: boolean
  onOpen: () => void
}

// Site-wide CSP disallows blob: URIs in img-src. We fetch with the auth
// Bearer (so the API proxy can call media-service), then convert the
// blob to a data: URL — data: is allowed by the existing img-src.
async function blobToDataUrl(blob: Blob): Promise<string> {
  return await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result === 'string') resolve(result)
      else reject(new Error('FileReader returned non-string'))
    }
    reader.onerror = () => reject(reader.error ?? new Error('FileReader error'))
    reader.readAsDataURL(blob)
  })
}

function MediaThumb({ id, isVideo, onOpen }: ThumbProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [errored, setErrored] = useState(false)

  useEffect(() => {
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect -- намеренный сброс состояния ошибки перед загрузкой медиа при смене id
    setErrored(false)
    twaClient
      .get(`/api/v2/media/${id}/file`, { responseType: 'blob' })
      .then((r) => blobToDataUrl(r.data as Blob))
      .then((dataUrl) => {
        if (!cancelled) setUrl(dataUrl)
      })
      .catch(() => {
        if (!cancelled) setErrored(true)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  // TWA-21: distinct error state — broken-image icon instead of a blank
  // disabled tile that's indistinguishable from "still loading".
  if (errored) {
    return (
      <div className="w-20 h-20 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-400">
        <ImageOff size={20} />
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={!url}
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
  const { t } = useTranslation()
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  // TWA-26: Escape closes the lightbox (desktop / browser-wrapper expectation;
  // the in-Telegram BackButton path is handled separately by the host page).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    twaClient
      .get(`/api/v2/media/${id}/file`, { responseType: 'blob' })
      .then((r) => blobToDataUrl(r.data as Blob))
      .then((dataUrl) => {
        if (!cancelled) setUrl(dataUrl)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
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
      {/* TWA-21: surface load failure instead of an eternal "…" spinner. */}
      {failed ? (
        <div className="flex flex-col items-center text-white/80 gap-2" onClick={(e) => e.stopPropagation()}>
          <ImageOff size={40} />
          <span className="text-[14px]">{t('twa.detail.mediaLoadError')}</span>
        </div>
      ) : url ? (
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
