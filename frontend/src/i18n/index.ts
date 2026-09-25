import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import ru from './locales/ru.json'
import uz from './locales/uz.json'
import uzCyrl from './locales/uz_cyrl.json'

/**
 * Узбекская кириллица (users.language = uz_cyrl). Переведён только простой
 * режим исполнителя (twa.simple.*); остальное — латиницей, затем русским.
 * Код языка i18next совпадает со значением профиля; для Intl/`<html lang>`
 * он невалиден (подчёркивание) — см. toBcp47.
 */
export const UZ_CYRL = 'uz_cyrl'

/** Код языка i18next → BCP 47 для Intl и атрибута lang. */
export function toBcp47(lng: string): string {
  return lng === UZ_CYRL ? 'uz-Cyrl' : lng
}

// Detect Telegram WebApp language (for TWA context)
function getTelegramLanguage(): string | undefined {
  try {
    const tg = (window as unknown as {
      Telegram?: { WebApp?: { initDataUnsafe?: { user?: { language_code?: string } } } }
    }).Telegram?.WebApp
    const lang = tg?.initDataUnsafe?.user?.language_code
    if (lang === 'uz') return 'uz'
    if (lang) return 'ru' // any other language falls back to Russian
  } catch {
    // Not in Telegram context
  }
  return undefined
}

const telegramLang = getTelegramLanguage()

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ru: { translation: ru },
      uz: { translation: uz },
      [UZ_CYRL]: { translation: uzCyrl },
    },
    fallbackLng: { [UZ_CYRL]: ['uz', 'ru'], default: ['ru'] },
    interpolation: { escapeValue: false },
    ...(telegramLang
      ? { lng: telegramLang } // Telegram language takes priority
      : {
          detection: {
            order: ['localStorage', 'navigator'],
            caches: ['localStorage'],
          },
        }),
  })

i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = toBcp47(lng)
})

export default i18n
