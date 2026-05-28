import { useRef, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { Camera, Image as ImageIcon, X } from 'lucide-react'

interface Props {
  files: File[]
  onChange: (files: File[]) => void
  maxFiles?: number
}

export default function PhotoUploader({ files, onChange, maxFiles = 5 }: Props) {
  const { t } = useTranslation()
  const { haptic } = useTelegramSDK()
  const cameraRef = useRef<HTMLInputElement>(null)
  const galleryRef = useRef<HTMLInputElement>(null)

  // Stable blob URLs tied to file identity; revoked on file removal or unmount
  // (TWA-10). Avoids inline URL.createObjectURL on every render.
  const urls = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files])
  useEffect(() => {
    return () => urls.forEach((u) => URL.revokeObjectURL(u))
  }, [urls])

  const handleAdd = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newFiles = Array.from(e.target.files || [])
    const combined = [...files, ...newFiles].slice(0, maxFiles)
    onChange(combined)
    haptic('selection')
    // Reset both inputs so the same file can be picked again if needed.
    if (cameraRef.current) cameraRef.current.value = ''
    if (galleryRef.current) galleryRef.current.value = ''
  }

  const handleRemove = (index: number) => {
    onChange(files.filter((_, i) => i !== index))
    haptic('impact')
  }

  const canAddMore = files.length < maxFiles

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-2">
        {files.map((_, i) => (
          <div key={i} className="relative w-20 h-20 rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700">
            <img
              src={urls[i]}
              alt=""
              className="w-full h-full object-cover"
            />
            <button
              onClick={() => handleRemove(i)}
              className="absolute top-0.5 right-0.5 w-5 h-5 bg-black/60 rounded-full flex items-center justify-center"
            >
              <X size={12} className="text-white" />
            </button>
          </div>
        ))}
        {canAddMore && (
          <>
            {/* TWA-18: explicit camera vs. gallery actions. The previous single
                tile used capture="environment" which forces the OS camera and
                blocks gallery selection on iOS — now two side-by-side tiles. */}
            <button
              type="button"
              onClick={() => cameraRef.current?.click()}
              className="w-20 h-20 rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-600 flex flex-col items-center justify-center text-gray-400 active:scale-95 transition-transform"
            >
              <Camera size={20} />
              <span className="text-[10px] mt-0.5">{files.length}/{maxFiles}</span>
            </button>
            <button
              type="button"
              onClick={() => galleryRef.current?.click()}
              className="w-20 h-20 rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-600 flex flex-col items-center justify-center text-gray-400 active:scale-95 transition-transform"
            >
              <ImageIcon size={20} />
              <span className="text-[10px] mt-0.5">Галерея</span>
            </button>
          </>
        )}
      </div>
      {/* TWA-32: when the limit is hit both add-tiles disappear; without this
          the user can't tell whether adding is broken or simply capped. */}
      {!canAddMore && (
        <p className="text-[11px] text-gray-400 mb-1">{t('twa.photo.maxFiles', { count: maxFiles })}</p>
      )}
      {/* Camera-only: capture attribute opens the OS camera directly. */}
      <input
        ref={cameraRef}
        type="file"
        accept="image/*,video/*"
        capture="environment"
        onChange={handleAdd}
        className="hidden"
      />
      {/* Gallery / file picker: no capture attribute → OS shows the regular
          file/photo chooser (existing photos + Files app on iOS). */}
      <input
        ref={galleryRef}
        type="file"
        accept="image/*,video/*"
        multiple
        onChange={handleAdd}
        className="hidden"
      />
    </div>
  )
}
