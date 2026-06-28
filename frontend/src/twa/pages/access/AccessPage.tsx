import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import VehiclesTab from './VehiclesTab'
import PassesTab from './PassesTab'
import EventsTab from './EventsTab'
import SpotsTab from './SpotsTab'

type Segment = 'vehicles' | 'spots' | 'passes' | 'events'

const SEGMENTS: Segment[] = ['vehicles', 'spots', 'passes', 'events']

/**
 * Раздел «Контроль доступа» жителя (applicant).
 *
 * Один экран с сегментным переключателем: Авто / Пропуска / Проезды. Маршрут
 * `/twa/app/access`; вход через таб «Доступ» в ApplicantTabs. Гейтинг по роли
 * applicant — на уровне роутера (RoleGuard required="applicant").
 */
export default function AccessPage() {
  const { t } = useTranslation()
  const [segment, setSegment] = useState<Segment>('vehicles')

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-3">
        {t('twa.access.title')}
      </h1>

      <div className="flex gap-2 mb-4">
        {SEGMENTS.map((s) => (
          <button
            key={s}
            onClick={() => setSegment(s)}
            className={`px-4 py-1.5 rounded-full text-[13px] font-medium transition-colors ${
              segment === s
                ? 'bg-emerald-500 text-white'
                : 'bg-gray-200 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
            }`}
          >
            {t(`twa.access.segments.${s}`)}
          </button>
        ))}
      </div>

      {segment === 'vehicles' && <VehiclesTab />}
      {segment === 'spots' && <SpotsTab />}
      {segment === 'passes' && <PassesTab />}
      {segment === 'events' && <EventsTab />}
    </div>
  )
}
