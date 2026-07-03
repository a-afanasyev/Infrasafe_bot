import { useEffect, useState, useCallback } from 'react'

interface TelegramHapticFeedback {
  impactOccurred: (style: string) => void
  notificationOccurred: (type: string) => void
  selectionChanged: () => void
}

interface TelegramBackButton {
  show: () => void
  hide: () => void
  onClick: (cb: () => void) => void
  offClick: (cb: () => void) => void
}

export interface TelegramWebApp {
  ready: () => void
  expand: () => void
  close: () => void
  initData: string
  initDataUnsafe: Record<string, unknown>
  themeParams: Record<string, string>
  colorScheme: 'light' | 'dark'
  HapticFeedback?: TelegramHapticFeedback
  BackButton?: TelegramBackButton
}

function getTg(): TelegramWebApp | null {
  return (window as unknown as { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp ?? null
}

/**
 * Telegram WebApp SDK wrapper.
 *
 * TWA-05: initData is read into state and re-evaluated after ready(), so
 * callers that depend on it (useTWAAuth) re-render once the SDK script has
 * finished injecting the real value. The previous module-scope `tg` read
 * captured an empty initData if the Telegram script loaded after our bundle
 * — that pushed the first authenticate() call into the localStorage-refresh
 * fallback even on a fresh open.
 */
export function useTelegramSDK() {
  const [tg, setTg] = useState<TelegramWebApp | null>(() => getTg())
  const [initData, setInitData] = useState<string>(() => getTg()?.initData ?? '')

  useEffect(() => {
    let cancelled = false

    const attach = () => {
      const t = getTg()
      if (!t) return false
      try {
        t.ready()
        t.expand()
      } catch { /* SDK может быть недоступен вне Telegram — игнорируем */ }
      if (cancelled) return true
      setTg(t)
      if (t.initData) setInitData(t.initData)
      return true
    }

    if (attach()) return

    // Telegram script can finish injection a tick later — poll briefly.
    const intervalId = window.setInterval(() => {
      if (attach()) window.clearInterval(intervalId)
    }, 100)
    const timeoutId = window.setTimeout(() => {
      window.clearInterval(intervalId)
    }, 3000)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
      window.clearTimeout(timeoutId)
    }
  }, [])

  const haptic = useCallback((type: 'impact' | 'notification' | 'selection' = 'impact') => {
    try {
      if (type === 'impact') tg?.HapticFeedback?.impactOccurred('light')
      else if (type === 'notification') tg?.HapticFeedback?.notificationOccurred('success')
      else tg?.HapticFeedback?.selectionChanged()
    } catch { /* HapticFeedback отсутствует в старых клиентах — игнорируем */ }
  }, [tg])

  const showBackButton = useCallback((onClick: () => void) => {
    tg?.BackButton?.show()
    tg?.BackButton?.onClick(onClick)
    return () => {
      tg?.BackButton?.hide()
      tg?.BackButton?.offClick(onClick)
    }
  }, [tg])

  return {
    tg,
    haptic,
    showBackButton,
    themeParams: tg?.themeParams ?? {},
    colorScheme: tg?.colorScheme ?? 'light',
    initData,
    initDataUnsafe: tg?.initDataUnsafe ?? {},
    close: () => tg?.close(),
  }
}
