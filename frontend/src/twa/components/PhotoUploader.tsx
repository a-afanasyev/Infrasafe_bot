import { useRef } from 'react'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { Camera, X } from 'lucide-react'

interface Props {
  files: File[]
  onChange: (files: File[]) => void
  maxFiles?: number
}

export default function PhotoUploader({ files, onChange, maxFiles = 5 }: Props) {
  const { haptic } = useTelegramSDK()
  const inputRef = useRef<HTMLInputElement>(null)

  const handleAdd = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newFiles = Array.from(e.target.files || [])
    const combined = [...files, ...newFiles].slice(0, maxFiles)
    onChange(combined)
    haptic('selection')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleRemove = (index: number) => {
    onChange(files.filter((_, i) => i !== index))
    haptic('impact')
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-2">
        {files.map((file, i) => (
          <div key={i} className="relative w-20 h-20 rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700">
            <img
              src={URL.createObjectURL(file)}
              alt=""
              className="w-full h-full object-cover"
              onLoad={(e) => URL.revokeObjectURL((e.target as HTMLImageElement).src)}
            />
            <button
              onClick={() => handleRemove(i)}
              className="absolute top-0.5 right-0.5 w-5 h-5 bg-black/60 rounded-full flex items-center justify-center"
            >
              <X size={12} className="text-white" />
            </button>
          </div>
        ))}
        {files.length < maxFiles && (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="w-20 h-20 rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-600 flex flex-col items-center justify-center text-gray-400 active:scale-95 transition-transform"
          >
            <Camera size={20} />
            <span className="text-[10px] mt-0.5">{files.length}/{maxFiles}</span>
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*,video/*"
        multiple
        capture="environment"
        onChange={handleAdd}
        className="hidden"
      />
    </div>
  )
}
