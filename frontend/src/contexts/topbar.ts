import { createContext, useContext } from 'react'
import type { ReactNode } from 'react'

// Контекст и хук вынесены из TopbarContext.tsx, чтобы файл-провайдер
// экспортировал только компонент (react-refresh/only-export-components).
export interface TopbarContextValue {
  actions: ReactNode
  setActions: (node: ReactNode) => void
  clearActions: () => void
}

export const TopbarContext = createContext<TopbarContextValue>({
  actions: null,
  setActions: () => {},
  clearActions: () => {},
})

export function useTopbar() {
  return useContext(TopbarContext)
}
