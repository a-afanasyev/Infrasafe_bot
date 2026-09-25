import { useEffect, useState, type RefObject } from 'react'

/**
 * Фото плиток — полноразмерные файлы медиа-сервиса. Чтобы список на плохой
 * сети не качал всё разом: грузим только видимые плитки (IntersectionObserver)
 * и не больше MAX_PARALLEL файлов одновременно.
 */
export const MAX_PARALLEL = 3

let active = 0
const waiting: (() => void)[] = []

function release() {
  active -= 1
  waiting.shift()?.()
}

/** Выполнить загрузку в общей очереди медиа (≤ MAX_PARALLEL параллельно). */
export function limitMedia<T>(task: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const start = () => {
      active += 1
      task().then(resolve, reject).finally(release)
    }
    if (active < MAX_PARALLEL) start()
    else waiting.push(start)
  })
}

/** Элемент попал в экран хотя бы раз (без IntersectionObserver — сразу true). */
export function useInView(ref: RefObject<Element | null>): boolean {
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    if (seen || !ref.current || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true)
          observer.disconnect()
        }
      },
      { rootMargin: '200px' },
    )
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [ref, seen])
  return seen
}
