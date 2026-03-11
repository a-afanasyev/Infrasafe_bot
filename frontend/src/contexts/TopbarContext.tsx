import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'

interface TopbarContextValue {
  actions: ReactNode
  setActions: (node: ReactNode) => void
  clearActions: () => void
}

const TopbarContext = createContext<TopbarContextValue>({
  actions: null,
  setActions: () => {},
  clearActions: () => {},
})

export function TopbarProvider({ children }: { children: ReactNode }) {
  const [actions, setActionsState] = useState<ReactNode>(null)

  const setActions = (node: ReactNode) => setActionsState(node)
  const clearActions = () => setActionsState(null)

  return (
    <TopbarContext.Provider value={{ actions, setActions, clearActions }}>
      {children}
    </TopbarContext.Provider>
  )
}

export function useTopbar() {
  return useContext(TopbarContext)
}

export { TopbarContext }
