import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../twaClient'

// uz_cyrl — своя локаль (переведён простой режим, остальное i18next
// добирает из uz, затем ru — см. fallbackLng в i18n/index.ts).
const SUPPORTED = ['ru', 'uz', 'uz_cyrl'] as const

interface ProfileResponse {
  language?: string | null
}

/**
 * Язык TWA = язык профиля (users.language — выбран в боте или в профиле TWA).
 * i18n стартует с Telegram language_code (фолбэк до загрузки профиля), после
 * загрузки профиля применяем его язык. Общий ключ ['twa', 'profile'] с
 * RoleGuard/ProfilePage — лишнего запроса нет, а смена языка в профиле
 * (PATCH + invalidate) сюда же и возвращается.
 */
export function useProfileLanguage() {
  const { i18n } = useTranslation()
  const query = useQuery<ProfileResponse>({
    queryKey: ['twa', 'profile'],
    queryFn: () => twaClient.get('/api/v2/profile').then((r) => r.data),
    staleTime: 60_000,
  })
  const lang = query.data?.language

  useEffect(() => {
    if (lang && (SUPPORTED as readonly string[]).includes(lang) && i18n.language !== lang) {
      i18n.changeLanguage(lang)
    }
  }, [lang, i18n])

  return query
}
