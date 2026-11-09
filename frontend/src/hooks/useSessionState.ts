import { useCallback, useState } from 'react'

/** `useState`, переживающий размонтирование страницы в пределах вкладки.
 *
 *  Фильтры списков иначе сбрасывались при уходе в карточку и «Назад».
 *  sessionStorage (не localStorage): новая вкладка начинает с чистых фильтров.
 *  Недоступное хранилище (приватный режим) — обычный useState. */
export function useSessionState<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = sessionStorage.getItem(key)
      return raw === null ? initial : (JSON.parse(raw) as T)
    } catch { return initial }
  })
  const set = useCallback((v: T) => {
    setValue(v)
    try { sessionStorage.setItem(key, JSON.stringify(v)) } catch { /* хранилище недоступно — только память */ }
  }, [key])
  return [value, set]
}
