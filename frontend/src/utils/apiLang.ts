import { useTranslation } from 'react-i18next'

/**
 * Язык интерфейса → параметр `lang` API (`ru|uz`). Вынесено из useElevators,
 * чтобы TWA-код мог пользоваться им, не подтягивая дашбордный `apiClient`.
 */
export type ApiLang = 'ru' | 'uz'

/** Всё, что не uz, — ru. */
export function normalizeApiLang(language: string | undefined): ApiLang {
  return language?.toLowerCase().startsWith('uz') ? 'uz' : 'ru'
}

export function useApiLang(): ApiLang {
  const { i18n } = useTranslation()
  return normalizeApiLang(i18n.language)
}
