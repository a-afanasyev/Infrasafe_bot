import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'

interface ScaledPreviewProps {
  // Ширина «экрана», в которой рендерится содержимое (табло — ТВ-страница).
  width: number
  children: ReactNode
}

// Миниатюра широкой страницы: содержимое раскладывается в `width` пикселей и
// уменьшается до ширины колонки превью. Без этого табло в колонке ~600px
// раскладывалось как узкий экран, которого в холле не бывает.
export default function ScaledPreview({ width, children }: ScaledPreviewProps) {
  const outerRef = useRef<HTMLDivElement>(null)
  const innerRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)
  const [height, setHeight] = useState<number | undefined>(undefined)

  useLayoutEffect(() => {
    const outer = outerRef.current
    const inner = innerRef.current
    if (!outer || !inner || typeof ResizeObserver === 'undefined') return
    const update = () => {
      const next = Math.min(1, outer.clientWidth / width)
      setScale(next)
      setHeight(inner.scrollHeight * next)
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(outer)
    observer.observe(inner)
    return () => observer.disconnect()
  }, [width])

  return (
    <div ref={outerRef} style={{ width: '100%', height, overflow: 'hidden' }}>
      <div ref={innerRef} style={{ width, transform: `scale(${scale})`, transformOrigin: 'top left' }}>
        {children}
      </div>
    </div>
  )
}
