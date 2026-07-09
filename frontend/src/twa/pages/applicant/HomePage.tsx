import { useQuery } from '@tanstack/react-query'
import type { TwaAnnouncement } from '../../types'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import { Bell, Phone, Clock } from 'lucide-react'
import PullToRefresh from '../../components/PullToRefresh'

export default function HomePage() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language.startsWith('uz') ? 'uz' : 'ru'
  const { data } = useQuery({
    queryKey: ['twa', 'announcements', lang],
    queryFn: () => twaClient.get('/api/v2/announcements', { params: { lang } }).then(r => r.data),
    staleTime: 60_000,
  })

  return (
    <PullToRefresh queryKeys={[['twa', 'announcements', lang]]}>
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.home.title')}</h1>

      {data?.announcements?.map((a: TwaAnnouncement) => (
        <div key={a.id} className="bg-white dark:bg-gray-800 rounded-2xl p-4 mb-3 border border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-2">
            {a.type === 'contact' ? <Phone size={16} className="text-emerald-500" /> : <Bell size={16} className="text-blue-500" />}
            <span className="font-semibold text-[14px] text-gray-900 dark:text-gray-100">{a.title}</span>
          </div>
          <p className="text-[13px] text-gray-600 dark:text-gray-400 whitespace-pre-line">{a.body}</p>
        </div>
      ))}

      {data?.working_hours && (
        <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-2xl p-4 border border-emerald-100 dark:border-emerald-800">
          <div className="flex items-center gap-2 mb-1">
            <Clock size={16} className="text-emerald-600" />
            <span className="font-semibold text-[13px] text-emerald-800 dark:text-emerald-300">{t('twa.home.workingHours')}</span>
          </div>
          <span className="text-[13px] text-emerald-700 dark:text-emerald-400 whitespace-pre-line">{data.working_hours}</span>
        </div>
      )}
    </div>
    </PullToRefresh>
  )
}
