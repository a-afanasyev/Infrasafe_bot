import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Sparkles } from 'lucide-react'
import { usePublicCleaningBuilding } from '../../../hooks/usePublicCleaning'
import { useResidentBuildings } from '../../hooks/useResidentBuildings'

/** Карточка на главной приложения жителя: видна, если уборка дома показывается жителям. */
export default function ResidentCleaningEntry() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const buildings = useResidentBuildings()
  const view = usePublicCleaningBuilding(buildings.data?.[0]?.id ?? null)
  if (!view.data) return null
  const done = view.data.entrances.filter((e) => e.state === 'done').length
  const planned = view.data.entrances.filter((e) => e.state !== 'none').length
  return (
    <button
      type="button" onClick={() => navigate('/twa/app/cleaning')} data-testid="resident-cleaning-entry"
      className="mb-3 flex w-full items-center gap-3 rounded-2xl border border-gray-100 bg-white p-4 text-left dark:border-gray-700 dark:bg-gray-800"
    >
      <Sparkles size={22} className="text-emerald-600" aria-hidden />
      <span className="flex flex-col">
        <span className="text-[14px] font-semibold text-gray-900 dark:text-gray-100">{t('twa.residentCleaning.title')}</span>
        <span className="text-[13px] text-gray-600 dark:text-gray-400">
          {planned === 0 ? t('twa.residentCleaning.noneToday') : t('twa.residentCleaning.summary', { done, total: planned })}
        </span>
      </span>
    </button>
  )
}
