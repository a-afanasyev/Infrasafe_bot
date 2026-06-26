import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Maximize2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'

/**
 * Фото проезда для уполномоченных ролей (§11): отдельно ОБЗОРНОЕ фото авто и
 * фото НОМЕРА. Два подписанных блока в стиле УК (карточки/бордеры темы).
 * Клик по фото — увеличение (lightbox на ui/dialog). Пустое состояние «Нет фото».
 *
 * Размеры: compact — миниатюры для карточки очереди; full — крупно для детали.
 * Live-лента фото НЕ показывает (PD-safe) — этот компонент в ней не используется.
 */

type PhotoSize = 'compact' | 'full'

interface AccessPhotosProps {
  overviewUrl?: string | null
  plateUrl?: string | null
  size?: PhotoSize
  className?: string
}

// Пропорции блоков: обзор ~16:9, номер — широкий узкий.
const OVERVIEW_RATIO = 'aspect-[16/9]'
const PLATE_RATIO = 'aspect-[16/9]'
const PLATE_RATIO_FULL = 'aspect-[4/1]'

interface PhotoTileProps {
  label: string
  url?: string | null
  ratio: string
  size: PhotoSize
  emptyText: string
  enlargeText: string
  onEnlarge: (url: string) => void
}

function PhotoTile({ label, url, ratio, size, emptyText, enlargeText, onEnlarge }: PhotoTileProps) {
  const hasPhoto = Boolean(url && url.trim() !== '')
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[10px] font-bold uppercase tracking-wider text-text-muted">{label}</span>
      {hasPhoto ? (
        <button
          type="button"
          onClick={() => onEnlarge(url as string)}
          title={enlargeText}
          aria-label={enlargeText}
          className={cn(
            'group relative w-full overflow-hidden rounded-default border border-border-default bg-bg-surface',
            'focus:outline-none focus:ring-2 focus:ring-accent',
            ratio,
          )}
        >
          <img
            src={url as string}
            alt={label}
            loading="lazy"
            className="h-full w-full object-cover"
          />
          <span className="pointer-events-none absolute right-1.5 top-1.5 rounded-sm bg-black/55 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100">
            <Maximize2 className={size === 'compact' ? 'h-3 w-3' : 'h-3.5 w-3.5'} />
          </span>
        </button>
      ) : (
        <div
          className={cn(
            'flex w-full items-center justify-center rounded-default border border-dashed border-border-default bg-bg-surface text-[12px] text-text-muted',
            ratio,
          )}
        >
          {emptyText}
        </div>
      )}
    </div>
  )
}

export default function AccessPhotos({
  overviewUrl,
  plateUrl,
  size = 'full',
  className,
}: AccessPhotosProps) {
  const { t } = useTranslation()
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)

  const emptyText = t('accessControl.photos.none')
  const enlargeText = t('accessControl.photos.enlarge')
  const plateRatio = size === 'full' ? PLATE_RATIO_FULL : PLATE_RATIO

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      <div
        className={cn(
          'grid gap-3',
          // На детали — обзор шире номера; в компакте — две равные миниатюры.
          size === 'full' ? 'grid-cols-1 sm:grid-cols-[2fr_1fr]' : 'grid-cols-2',
        )}
      >
        <PhotoTile
          label={t('accessControl.photos.vehicle')}
          url={overviewUrl}
          ratio={OVERVIEW_RATIO}
          size={size}
          emptyText={emptyText}
          enlargeText={enlargeText}
          onEnlarge={setLightboxUrl}
        />
        <PhotoTile
          label={t('accessControl.photos.plate')}
          url={plateUrl}
          ratio={plateRatio}
          size={size}
          emptyText={emptyText}
          enlargeText={enlargeText}
          onEnlarge={setLightboxUrl}
        />
      </div>

      <Dialog open={lightboxUrl !== null} onOpenChange={(open) => !open && setLightboxUrl(null)}>
        <DialogContent className="max-w-4xl bg-bg-card p-3">
          <DialogTitle className="sr-only">{enlargeText}</DialogTitle>
          {lightboxUrl && (
            <img
              src={lightboxUrl}
              alt={enlargeText}
              loading="lazy"
              className="max-h-[80vh] w-full rounded-sm object-contain"
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
