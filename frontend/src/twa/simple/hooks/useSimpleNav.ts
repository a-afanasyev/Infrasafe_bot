import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'

/**
 * «Назад» — системная кнопка Telegram. Цель задаём явно (а не history -1):
 * экран, открытый по ссылке из бота, иначе «уходил назад» в никуда.
 * `intercept` — вернуть true, если нажатие поглощено экраном (закрыть фото).
 */
export function useBackTo(path: string, intercept?: () => boolean): void {
  const navigate = useNavigate()
  const { showBackButton } = useTelegramSDK()
  useEffect(
    () =>
      showBackButton(() => {
        if (intercept?.()) return
        navigate(path)
      }),
    [showBackButton, navigate, path, intercept],
  )
}

/** navigator.onLine с подпиской на online/offline. */
export function useOnline(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))
  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])
  return online
}

/** «ЧЧ:ММ» от начала смены, тикает раз в секунду. */
export function useElapsed(startIso: string | null | undefined): string {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!startIso) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [startIso])
  if (!startIso) return ''
  const start = Date.parse(startIso)
  if (Number.isNaN(start)) return ''
  const diff = Math.max(0, now - start)
  const h = Math.floor(diff / 3_600_000)
  const m = Math.floor((diff % 3_600_000) / 60_000)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
