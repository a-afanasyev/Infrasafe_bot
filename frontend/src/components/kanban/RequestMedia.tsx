import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { ImageOff, X as XIcon } from 'lucide-react'
import { useHasAnyRole } from '../../hooks/useHasRole'
import { useMediaBlob, useRequestMediaList } from '../../hooks/useRequestMedia'
import { useRequestMediaUpload } from '../../hooks/useRequestMediaUpload'
import MediaUploadTile from './MediaUploadTile'

// Категории фотоотчёта — зеркалят FileCategories media-прокси (SEC-021 whitelist).
const COMPLETION_CATEGORIES = new Set(['completion_photo', 'completion_video', 'completion_document'])

/**
 * Медиа карточки заявки: фото заявки + фотоотчёт (менеджер может дозагрузить).
 * Раздел скрывается, если медиа нет и грузить некому.
 *
 * Байты грузятся через apiClient и конвертируются в data: URL (CSP запрещает
 * blob: в img-src) — без этого фото к заявке не отображались на канбане вовсе.
 */
export default function RequestMedia({ requestNumber }: { requestNumber: string }) {
  const { t } = useTranslation()
  const [lightboxId, setLightboxId] = useState<number | null>(null)
  // Менеджер прикладывает и фото заявки (проблема пришла по телефону, фото —
  // в мессенджер), и фотоотчёт (та же пара ролей, что и остальные менеджерские
  // мутации заявки; backend-гейт — check_request_access).
  const canUpload = useHasAnyRole(['manager', 'system_admin'])

  const { data: items = [], isError } = useRequestMediaList(requestNumber)

  const uploadRequest = useRequestMediaUpload({ requestNumber, kind: 'request' })
  const uploadCompletion = useRequestMediaUpload({ requestNumber, kind: 'completion' })

  const requestItems = items.filter((m) => !COMPLETION_CATEGORIES.has(m.category ?? ''))
  const completionItems = items.filter((m) => COMPLETION_CATEGORIES.has(m.category ?? ''))

  // Сбой media-service — не «фото нет»: прокси отвечает ошибкой, а не [].
  if (items.length === 0 && !canUpload && !isError) return null

  return (
    <div className="flex flex-col gap-3">
      {isError && <div className="text-[12px] text-red">{t('kanban.mediaListError')}</div>}
      {(requestItems.length > 0 || canUpload) && (
        <div>
          <div className="text-[11px] font-bold text-text-muted uppercase tracking-wide font-[family-name:var(--font-display)] mb-2">
            {t('kanban.photos')}
          </div>
          <div className="flex flex-wrap gap-2">
            {requestItems.map((m) => (
              <MediaThumb key={m.id} id={m.id} isVideo={m.file_type === 'video'} onOpen={() => setLightboxId(m.id)} />
            ))}
            {canUpload && (
              <MediaUploadTile
                label={t('kanban.addRequestPhotos')}
                testId="request-upload-input"
                disabled={uploadRequest.isPending}
                onFiles={(files) => uploadRequest.mutate(files)}
              />
            )}
          </div>
        </div>
      )}
      {(completionItems.length > 0 || canUpload) && (
        <div>
          <div className="text-[11px] font-bold text-text-muted uppercase tracking-wide font-[family-name:var(--font-display)] mb-2">
            {t('kanban.completionPhotos')}
          </div>
          <div className="flex flex-wrap gap-2">
            {completionItems.map((m) => (
              <MediaThumb key={m.id} id={m.id} isVideo={m.file_type === 'video'} onOpen={() => setLightboxId(m.id)} />
            ))}
            {canUpload && (
              <MediaUploadTile
                label={t('kanban.addWorkPhotos')}
                testId="completion-upload-input"
                disabled={uploadCompletion.isPending}
                onFiles={(files) => uploadCompletion.mutate(files)}
              />
            )}
          </div>
        </div>
      )}
      {lightboxId !== null && (
        <MediaLightbox key={lightboxId} id={lightboxId} onClose={() => setLightboxId(null)} />
      )}
    </div>
  )
}

function MediaThumb({ id, isVideo, onOpen }: { id: number; isVideo: boolean; onOpen: () => void }) {
  const { t } = useTranslation()
  // FE-11: cache the blob data-URL by media id (shared queryKey with the
  // lightbox) so re-opening the modal or the viewer doesn't re-download.
  const { data: url, isError: errored } = useMediaBlob(id)

  if (errored) {
    return (
      <div className="w-20 h-20 rounded-lg border border-border-default bg-bg-surface flex items-center justify-center text-text-secondary" title={t('kanban.mediaError')}>
        <ImageOff size={18} />
      </div>
    )
  }
  return (
    <button
      type="button"
      onClick={onOpen}
      className="relative w-20 h-20 rounded-lg overflow-hidden border border-border-default bg-bg-surface"
    >
      {url ? (
        isVideo ? (
          <video src={url} className="w-full h-full object-cover" muted />
        ) : (
          <img src={url} alt="" className="w-full h-full object-cover" />
        )
      ) : (
        <div className="w-full h-full animate-pulse bg-bg-surface" />
      )}
      {isVideo && (
        <span className="absolute inset-0 flex items-center justify-center text-white text-lg drop-shadow">▶</span>
      )}
    </button>
  )
}

function MediaLightbox({ id, onClose }: { id: number; onClose: () => void }) {
  // FE-11: reuse the cached blob (shared media-blob key) — opening the
  // viewer for a thumb that already loaded is instant, no re-download.
  const { data: url, isError } = useMediaBlob(id)
  const isVideo = url?.startsWith('data:video') ?? false

  useEffect(() => {
    if (isError) onClose()
  }, [isError, onClose])

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/85 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 w-9 h-9 rounded-full bg-white/15 text-white flex items-center justify-center"
      >
        <XIcon size={18} />
      </button>
      {url && (
        isVideo ? (
          <video src={url} controls autoPlay className="max-w-full max-h-[85vh] rounded-lg" onClick={(e) => e.stopPropagation()} />
        ) : (
          <img src={url} alt="" className="max-w-full max-h-[85vh] rounded-lg object-contain" onClick={(e) => e.stopPropagation()} />
        )
      )}
    </div>
  )
}
