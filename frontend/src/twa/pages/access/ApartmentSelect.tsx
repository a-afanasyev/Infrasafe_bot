import { useTranslation } from 'react-i18next'
import type { ApartmentOption } from './types'

interface Props {
  apartments: ApartmentOption[]
  value: number | null
  onChange: (apartmentId: number) => void
}

/**
 * Выбор квартиры для access-формы.
 *
 * Если квартира одна — показываем её строкой (выбор не нужен, родитель
 * автоселектит). Если несколько — список кнопок. Пустой список обрабатывает
 * родитель (форма не рендерится).
 */
export default function ApartmentSelect({ apartments, value, onChange }: Props) {
  const { t } = useTranslation()

  if (apartments.length === 1) {
    return (
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] text-gray-700 dark:text-gray-300">
        🏠 {apartments[0].full_address}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <label className="block text-[12px] text-gray-500 dark:text-gray-400">
        {t('twa.access.apartment.select')}
      </label>
      {apartments.map((a) => (
        <button
          key={a.apartment_id}
          type="button"
          onClick={() => onChange(a.apartment_id)}
          className={`w-full text-left rounded-xl p-3 text-[13px] border transition-transform active:scale-[0.97] ${
            value === a.apartment_id
              ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-400 dark:border-emerald-700'
              : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
          }`}
        >
          🏠 {a.full_address}
        </button>
      ))}
    </div>
  )
}
