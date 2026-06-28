import { useLocation, useNavigate } from 'react-router-dom'
import { Home, ClipboardList, PlusCircle, CheckCircle, UserCircle, Car } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { twaClient } from '../twaClient'

interface Tab {
  path: string
  icon: React.ReactNode
  label: string
  badge?: number
}

interface Props {
  tabs: Tab[]
}

export default function BottomTabBar({ tabs }: Props) {
  const location = useLocation()
  const navigate = useNavigate()
  const { haptic } = useTelegramSDK()

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 px-2 pb-[env(safe-area-inset-bottom)] z-50">
      <div className="flex justify-around items-center h-14">
        {tabs.map((tab) => {
          const isActive = tab.path === '/twa/app' || tab.path === '/twa/exec'
            ? location.pathname === tab.path
            : location.pathname.startsWith(tab.path)
          return (
            <button
              key={tab.path}
              onClick={() => { haptic('selection'); navigate(tab.path) }}
              className={`flex flex-col items-center justify-center w-full h-full relative transition-colors ${
                isActive ? 'text-emerald-500' : 'text-gray-400 dark:text-gray-500'
              }`}
            >
              <div className="relative">
                {tab.icon}
                {(tab.badge ?? 0) > 0 && (
                  <span className="absolute -top-1 -right-2 bg-red-500 text-white text-[10px] font-bold rounded-full min-w-[16px] h-4 flex items-center justify-center px-1">
                    {tab.badge}
                  </span>
                )}
              </div>
              <span className="text-[10px] mt-0.5 font-medium">{tab.label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}

export function ApplicantTabs() {
  const { t } = useTranslation()
  // Self-fetch the acceptance count (shared cache with AcceptancePage) so the
  // tab badge reflects requests actually awaiting acceptance.
  const { data: acceptance = [] } = useQuery({
    queryKey: ['twa', 'acceptance'],
    queryFn: () => twaClient.get('/api/v2/requests/acceptance').then((r) => r.data),
    staleTime: 30_000,
  })
  const tabs: Tab[] = [
    { path: '/twa/app', icon: <Home size={20} />, label: t('twa.tabs.home') },
    { path: '/twa/app/requests', icon: <ClipboardList size={20} />, label: t('twa.tabs.requests') },
    { path: '/twa/app/create', icon: <PlusCircle size={22} />, label: t('twa.tabs.create') },
    { path: '/twa/app/acceptance', icon: <CheckCircle size={20} />, label: t('twa.tabs.acceptance'), badge: acceptance.length },
    { path: '/twa/app/access', icon: <Car size={20} />, label: t('twa.tabs.access') },
    { path: '/twa/app/profile', icon: <UserCircle size={20} />, label: t('twa.tabs.profile') },
  ]
  return <BottomTabBar tabs={tabs} />
}
