import { createContext, useContext } from 'react'

import { DEFAULT_DISPLAY_TZ, isValidTimeZone } from '../utils/timezone'

// Контекст и хук вынесены из DisplayTzProvider.tsx, чтобы файл-провайдер
// экспортировал только компонент (react-refresh/only-export-components) —
// тот же раскрой, что у topbar.ts / TopbarContext.tsx.

export const DisplayTzContext = createContext<string>(DEFAULT_DISPLAY_TZ)

export function useDisplayTz(): string {
  return useContext(DisplayTzContext)
}

// Rolling deploy делает `display_tz` опциональным на wire: старый бэкенд
// вернёт 200 без поля (тот же контракт «фронт впереди бэка», что закреплён
// тестом WorkReportsPage). Мусорные значения тоже деградируют в дефолт.
export function resolveDisplayTz(data: unknown): string {
  if (data && typeof data === 'object' && 'display_tz' in data) {
    const tz = (data as { display_tz?: unknown }).display_tz
    if (typeof tz === 'string' && isValidTimeZone(tz)) return tz
  }
  return DEFAULT_DISPLAY_TZ
}
