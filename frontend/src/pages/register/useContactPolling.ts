import { useCallback, useEffect, useRef, useState } from 'react'
import type { RegistrationContactStatus } from '../../hooks/useRegistration'

export const CONTACT_POLL_MS = 1500
export const CONTACT_TIMEOUT_MS = 30_000

export type PollState = 'idle' | 'polling' | 'timeout'

/**
 * После requestContact контакт уходит боту сообщением, а users.phone
 * появляется через API — опрашиваем contact-status до номера или таймаута.
 */
export function useContactPolling(
  ticket: string,
  contactStatus: (ticket: string) => Promise<RegistrationContactStatus>,
  onDone: (phone: string) => void,
) {
  const [state, setState] = useState<PollState>('idle')
  const timer = useRef<number | null>(null)
  const cancelled = useRef(false)

  const stop = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
  }, [])

  const start = useCallback(() => {
    stop()
    setState('polling')
    const startedAt = Date.now()
    const tick = async () => {
      let phone: string | null = null
      try {
        phone = (await contactStatus(ticket)).phone
      } catch {
        phone = null // временная ошибка сети — просто следующая попытка
      }
      if (cancelled.current) return
      if (phone) {
        setState('idle')
        onDone(phone)
        return
      }
      if (Date.now() - startedAt >= CONTACT_TIMEOUT_MS) {
        setState('timeout')
        return
      }
      timer.current = window.setTimeout(tick, CONTACT_POLL_MS)
    }
    void tick()
  }, [contactStatus, onDone, stop, ticket])

  useEffect(() => {
    cancelled.current = false
    return () => {
      cancelled.current = true
      stop()
    }
  }, [stop])

  return { state, start }
}
