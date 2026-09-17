import { useEffect, useState } from 'react'

/** Значение, «догоняющее» исходное после паузы `delayMs` — для серверного поиска по вводу. */
export function useDebouncedValue<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}
