import { useCallback, useState } from 'react'

/** `useState`, переживающий размонтирование страницы в пределах вкладки.
 *
 *  Фильтры списков иначе сбрасывались при уходе в карточку и «Назад».
 *  sessionStorage (не localStorage): новая вкладка начинает с чистых фильтров.
 *  Недоступное хранилище (приватный режим) — обычный useState.
 *  `isValid` отсекает испорченное/устаревшее значение — тогда `initial`. */
export function useSessionState<T>(
  key: string,
  initial: T,
  isValid: (v: unknown) => v is T,
): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = sessionStorage.getItem(key)
      if (raw === null) return initial
      const parsed: unknown = JSON.parse(raw)
      return isValid(parsed) ? parsed : initial
    } catch { return initial }
  })
  const set = useCallback((v: T) => {
    setValue(v)
    try { sessionStorage.setItem(key, JSON.stringify(v)) } catch { /* хранилище недоступно — только память */ }
  }, [key])
  return [value, set]
}

export const isString = (v: unknown): v is string => typeof v === 'string'
export const isBoolean = (v: unknown): v is boolean => typeof v === 'boolean'
export const isOffset = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 0
export const isIdOrNull = (v: unknown): v is number | null => v === null || Number.isInteger(v)
