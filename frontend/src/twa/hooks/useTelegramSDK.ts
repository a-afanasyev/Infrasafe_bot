import { useEffect, useCallback } from 'react'

const tg = (window as any).Telegram?.WebApp

export function useTelegramSDK() {
  useEffect(() => {
    tg?.ready()
    tg?.expand()
  }, [])

  const haptic = useCallback((type: 'impact' | 'notification' | 'selection' = 'impact') => {
    try {
      if (type === 'impact') tg?.HapticFeedback?.impactOccurred('light')
      else if (type === 'notification') tg?.HapticFeedback?.notificationOccurred('success')
      else tg?.HapticFeedback?.selectionChanged()
    } catch {}
  }, [])

  const showBackButton = useCallback((onClick: () => void) => {
    tg?.BackButton?.show()
    tg?.BackButton?.onClick(onClick)
    return () => {
      tg?.BackButton?.hide()
      tg?.BackButton?.offClick(onClick)
    }
  }, [])

  return {
    tg,
    haptic,
    showBackButton,
    themeParams: tg?.themeParams ?? {},
    colorScheme: tg?.colorScheme ?? 'light',
    initData: tg?.initData ?? '',
    initDataUnsafe: tg?.initDataUnsafe ?? {},
    close: () => tg?.close(),
  }
}
