import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import ru from './locales/ru.json'
import uz from './locales/uz.json'

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
    },
    fallbackLng: 'ru',
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
  document.documentElement.lang = lng
})

export default i18n
