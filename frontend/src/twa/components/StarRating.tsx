import { useState } from 'react'
import { Star } from 'lucide-react'
import { useTelegramSDK } from '../hooks/useTelegramSDK'

interface Props {
  value: number
  onChange: (val: number) => void
  size?: number
}

export default function StarRating({ value, onChange, size = 32 }: Props) {
  const [hover, setHover] = useState(0)
  const { haptic } = useTelegramSDK()

  return (
    <div className="flex gap-1 justify-center">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          onMouseEnter={() => setHover(star)}
          onMouseLeave={() => setHover(0)}
          onClick={() => { haptic('impact'); onChange(star) }}
          className="p-1 transition-transform active:scale-110"
        >
          <Star
            size={size}
            className={`transition-colors ${
              star <= (hover || value)
                ? 'fill-amber-400 text-amber-400'
                : 'fill-none text-gray-300 dark:text-gray-600'
            }`}
          />
        </button>
      ))}
    </div>
  )
}
