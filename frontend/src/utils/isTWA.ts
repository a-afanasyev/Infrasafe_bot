declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string
        ready: () => void
        expand: () => void
        close: () => void
        MainButton: {
          text: string
          show: () => void
          hide: () => void
          onClick: (fn: () => void) => void
        }
      }
    }
  }
}

export const isTWA = (): boolean =>
  typeof window !== 'undefined' && !!window.Telegram?.WebApp?.initData

export const getTWAInitData = (): string =>
  window.Telegram?.WebApp?.initData ?? ''
