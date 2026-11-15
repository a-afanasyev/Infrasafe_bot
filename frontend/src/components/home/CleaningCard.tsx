import { useTranslation } from 'react-i18next'
import { usePublicCleaningToday } from '../../hooks/usePublicCleaning'

interface CleaningCardProps {
  title: string
}

// «Уборка» на странице жителей: «убрано N из M домов» и строка по каждому дому.
// Счёт по домам, не по подъездам: дом убран, когда приняты все его задания дня.
// Данные — открытая сводка модуля «Уборка»; имён сотрудников и причин проверки
// в ней нет.
export default function CleaningCard({ title }: CleaningCardProps) {
  const { t } = useTranslation()
  const { data } = usePublicCleaningToday()

  return (
    <section className="rh-card rh-cleaning" aria-labelledby="rh-cleaning-heading">
      <div className="rh-section-heading">
        <div>
          <h2 id="rh-cleaning-heading">{title || t('home.cleaning.title')}</h2>
          <p>{t('home.cleaning.sub')}</p>
        </div>
      </div>
      {!data || !data.enabled || data.buildings.length === 0 ? (
        <p className="rh-empty">{data ? t('home.cleaning.empty') : '—'}</p>
      ) : (
        <div className="rh-cleaning-body">
          <div className="rh-cleaning-main">
            <span className="rh-metric-number rh-cleaning-number">
              {data.buildings_done}<span> / {data.buildings_total}</span>
            </span>
            <span className="rh-metric-caption">{t('home.cleaning.done')}</span>
          </div>
          <ul className="rh-cleaning-list">
            {data.buildings.map((building) => (
              <li key={building.building_id} className={`rh-cleaning-row rh-cleaning-row--${building.state}`}>
                <strong>{building.address}</strong>
                <span>{t(`home.cleaning.state.${building.state}`)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
