import { useRef } from 'react'
import { ImagePlus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { UPLOAD_ACCEPT } from './useRequestMediaUpload'

/**
 * Плитка «добавить» в ряду превью медиа + скрытый file-input. Одна на секцию
 * («Фото» заявки и «Фотоотчёт»), различаются подписью и testId.
 */
export default function MediaUploadTile({
  label,
  testId,
  disabled,
  onFiles,
}: {
  label: string
  testId: string
  disabled?: boolean
  onFiles: (files: File[]) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <>
      <button
        type="button"
        aria-label={label}
        title={label}
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className={cn(
          'w-20 h-20 rounded-lg border-2 border-dashed border-border-default bg-bg-surface',
          'flex flex-col items-center justify-center gap-0.5 text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors',
          disabled && 'animate-pulse cursor-wait',
        )}
      >
        <ImagePlus size={18} />
        <span className="text-[10px] leading-tight px-1 text-center">{label}</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={UPLOAD_ACCEPT}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          if (files.length > 0) onFiles(files)
          // Сброс, чтобы тот же файл можно было выбрать повторно.
          e.target.value = ''
        }}
        className="hidden"
        data-testid={testId}
      />
    </>
  )
}
