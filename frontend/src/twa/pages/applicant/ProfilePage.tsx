import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../../../api/client'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { Globe, MapPin, LogOut } from 'lucide-react'

export default function ProfilePage() {
  const { t, i18n } = useTranslation()
  const { haptic, close } = useTelegramSDK()
  const queryClient = useQueryClient()

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiClient.get('/api/v2/profile').then(r => r.data),
  })

  const { data: apartments = [] } = useQuery({
    queryKey: ['my-apartments'],
    queryFn: () => apiClient.get('/api/v2/profile/apartments').then(r => r.data),
  })

  const langMutation = useMutation({
    mutationFn: (lang: string) => apiClient.patch('/api/v2/profile', { language: lang }),
    onSuccess: (_, lang) => {
      i18n.changeLanguage(lang)
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      haptic('notification')
    },
  })

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.profile.title')}</h1>

      {profile && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center text-emerald-600 font-bold text-lg">
              {(profile.first_name?.[0] || 'U').toUpperCase()}
            </div>
            <div>
              <div className="font-semibold text-[15px] text-gray-900 dark:text-gray-100">
                {profile.first_name} {profile.last_name || ''}
              </div>
              <div className="text-[12px] text-gray-500">{profile.phone || profile.email || ''}</div>
            </div>
          </div>
        </div>
      )}

      {/* Apartments */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
        <div className="flex items-center gap-2 mb-2">
          <MapPin size={16} className="text-emerald-500" />
          <span className="font-semibold text-[13px]">{t('twa.profile.myAddresses')}</span>
        </div>
        {apartments.length === 0 && <p className="text-[12px] text-gray-400">{t('twa.profile.noAddresses')}</p>}
        {apartments.map((a: any) => (
          <div key={a.apartment_id} className="text-[12px] text-gray-600 dark:text-gray-400 py-1">{a.full_address}</div>
        ))}
      </div>

      {/* Language */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
        <div className="flex items-center gap-2 mb-2">
          <Globe size={16} className="text-blue-500" />
          <span className="font-semibold text-[13px]">{t('twa.profile.language')}</span>
        </div>
        <div className="flex gap-2">
          {['ru', 'uz'].map((lang) => (
            <button
              key={lang}
              onClick={() => langMutation.mutate(lang)}
              className={`px-4 py-1.5 rounded-full text-[12px] font-medium transition-colors ${
                i18n.language === lang
                  ? 'bg-emerald-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
              }`}
            >
              {lang === 'ru' ? 'Русский' : "O'zbek"}
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={close}
        className="w-full flex items-center justify-center gap-2 text-gray-400 text-[13px] py-4"
      >
        <LogOut size={14} />
        {t('twa.profile.close')}
      </button>
    </div>
  )
}
