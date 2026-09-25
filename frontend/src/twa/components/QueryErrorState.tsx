import { useTranslation } from 'react-i18next'

/**
 * Ошибка загрузки списка. Без неё сетевой сбой выглядел как пустой список
 * («Нет активных заданий») — исполнитель думал, что работы нет.
 */
export default function QueryErrorState({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <div role="alert" className="text-center py-12">
      <p className="text-[40px] mb-2">⚠️</p>
      <p className="text-gray-500 dark:text-gray-400 text-[14px] mb-3">{t('twa.errors.loadFailed')}</p>
      <button
        onClick={onRetry}
        className="px-4 py-2 rounded-xl bg-emerald-500 text-white text-[13px] font-semibold"
      >
        {t('twa.retry')}
      </button>
    </div>
  )
}
