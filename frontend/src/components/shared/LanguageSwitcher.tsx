import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

interface Props {
  className?: string
}

export default function LanguageSwitcher({ className }: Props) {
  const { i18n, t } = useTranslation()
  // resolvedLanguage: при браузерном «ru-RU» i18n.language ≠ 'ru', и первый клик
  // переключал бы на ru вместо uz.
  const isRu = (i18n.resolvedLanguage ?? i18n.language)?.startsWith('ru')

  const toggle = () => {
    i18n.changeLanguage(isRu ? 'uz' : 'ru')
  }

  return (
    <button
      onClick={toggle}
      className={cn(
        'inline-flex items-center gap-1 rounded-sm px-2 py-1 text-xs font-semibold transition-colors',
        'border border-border-default text-text-secondary hover:bg-bg-surface hover:text-text-primary',
        className,
      )}
      title={isRu ? t('language.switchToUz') : t('language.switchToRu')}
    >
      {isRu ? t('language.uz') : t('language.ru')}
    </button>
  )
}
