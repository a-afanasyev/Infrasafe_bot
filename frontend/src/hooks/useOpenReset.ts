import { useState } from 'react'

/**
 * Render-time сброс формы диалога при открытии (паттерн MaterialFormDialog /
 * ZoneFormDialog — без useEffect): `reset` вызывается на переходе closed→open.
 */
export function useOpenReset(open: boolean, reset: () => void): void {
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) reset()
  }
}
