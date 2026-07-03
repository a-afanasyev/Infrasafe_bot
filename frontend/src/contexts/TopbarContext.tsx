import { useCallback, useState } from 'react'
import type { ReactNode } from 'react'
import { TopbarContext } from './topbar'

export function TopbarProvider({ children }: { children: ReactNode }) {
  const [actions, setActionsState] = useState<ReactNode>(null)

  const setActions = useCallback((node: ReactNode) => setActionsState(node), [])
  const clearActions = useCallback(() => setActionsState(null), [])

  return (
    <TopbarContext.Provider value={{ actions, setActions, clearActions }}>
      {children}
    </TopbarContext.Provider>
  )
}
