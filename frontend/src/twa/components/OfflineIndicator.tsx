import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { WifiOff } from 'lucide-react'

export default function OfflineIndicator() {
  const { t } = useTranslation()
  const [isOffline, setIsOffline] = useState(!navigator.onLine)

  useEffect(() => {
    const goOffline = () => setIsOffline(true)
    const goOnline = () => setIsOffline(false)
    window.addEventListener('offline', goOffline)
    window.addEventListener('online', goOnline)
    return () => {
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('online', goOnline)
    }
  }, [])

  if (!isOffline) return null

  return (
    <div className="fixed top-0 left-0 right-0 z-[100] bg-red-500 text-white text-center py-1.5 text-[12px] font-medium flex items-center justify-center gap-1.5 animate-pulse">
      <WifiOff size={14} />
      {t('twa.offline') ?? 'Нет подключения'}
    </div>
  )
}
