import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { notifyError } from '../../utils/errors'
import RoleSwitchButton from '../../components/RoleSwitchButton'
import { Globe, Wrench, LogOut, MessageSquare, ChevronRight } from 'lucide-react'

export default function ExecutorProfilePage() {
  const { t, i18n } = useTranslation()
  const { haptic, close } = useTelegramSDK()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => twaClient.get('/api/v2/profile').then(r => r.data),
  })

  const langMutation = useMutation({
    mutationFn: (lang: string) => twaClient.patch('/api/v2/profile', { language: lang }),
    onSuccess: (_, lang) => {
      i18n.changeLanguage(lang)
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      haptic('notification')
    },
    onError: (err: unknown) => {
      notifyError(err)
    },
  })

  const specializations = profile?.specialization
    ? (typeof profile.specialization === 'string'
      ? (profile.specialization.startsWith('[')
        ? JSON.parse(profile.specialization)
        : [profile.specialization])
      : profile.specialization)
    : []

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.profile.title')}</h1>

      {profile && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center text-purple-600 font-bold text-lg">
              {(profile.first_name?.[0] || 'E').toUpperCase()}
            </div>
            <div>
              <div className="font-semibold text-[15px] text-gray-900 dark:text-gray-100">
                {profile.first_name} {profile.last_name || ''}
              </div>
              <div className="text-[12px] text-gray-500">{profile.phone || ''}</div>
            </div>
          </div>
        </div>
      )}

      {/* Switch to applicant mode (only for dual-role users) */}
      <RoleSwitchButton to="applicant" />

      {specializations.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
          <div className="flex items-center gap-2 mb-2">
            <Wrench size={16} className="text-purple-500" />
            <span className="font-semibold text-[13px]">{t('twa.exec.profile.specializations')}</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {specializations.map((s: string) => (
              <span key={s} className="bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400 text-[11px] px-2 py-0.5 rounded-full">{s}</span>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
        <div className="flex items-center gap-2 mb-2">
          <Globe size={16} className="text-blue-500" />
          <span className="font-semibold text-[13px]">{t('twa.profile.language')}</span>
        </div>
        <div className="flex gap-2">
          {['ru', 'uz'].map((lang) => (
            <button key={lang} onClick={() => langMutation.mutate(lang)}
              className={`px-4 py-1.5 rounded-full text-[12px] font-medium transition-colors ${
                i18n.language === lang ? 'bg-emerald-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
              }`}
            >{lang === 'ru' ? 'Русский' : "O'zbek"}</button>
          ))}
        </div>
      </div>

      {/* Обратная связь */}
      <button
        onClick={() => { haptic('selection'); navigate('/twa/feedback') }}
        className="w-full flex items-center justify-between bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3"
      >
        <span className="flex items-center gap-2">
          <MessageSquare size={16} className="text-amber-500" />
          <span className="font-semibold text-[13px]">{t('twa.feedback.title')}</span>
        </span>
        <ChevronRight size={16} className="text-gray-400" />
      </button>

      <button onClick={close} className="w-full flex items-center justify-center gap-2 text-gray-400 text-[13px] py-4">
        <LogOut size={14} /> {t('twa.profile.close')}
      </button>
    </div>
  )
}
