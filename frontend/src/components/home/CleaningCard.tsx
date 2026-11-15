import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { usePublicCleaningToday } from '../../hooks/usePublicCleaning'
import { formatTime } from '../../utils/timezone'

interface CleaningCardProps {
  title: string
}

// «Уборка» на странице жителей: «убрано N из M домов», полоса хода и строка по
// каждому дому. Счёт по домам, не по подъездам: дом убран, когда приняты все
// его задания дня. Подъезды и фото — на странице-обзоре /cleaning.
// Данные — открытая сводка модуля «Уборка»; имён сотрудников и причин проверки
// в ней нет.
export default function CleaningCard({ title }: CleaningCardProps) {
  const { t } = useTranslation()
  const { data } = usePublicCleaningToday()
  // Пока менеджер не включил показ ни одного дома, жителям блок не виден вовсе.
  if (data && (!data.enabled || data.buildings.length === 0)) return null
  const total = data?.buildings_total ?? 0
  const done = data?.buildings_done ?? 0

  return (
    <section className="rh-card rh-cleaning" aria-labelledby="rh-cleaning-heading">
      <div className="rh-section-heading">
        <div>
          <h2 id="rh-cleaning-heading">{title || t('home.cleaning.title')}</h2>
          <p>{t('home.cleaning.sub')}</p>
        </div>
        {data && <Link className="rh-small-action" to="/cleaning">{t('home.cleaning.all')} →</Link>}
      </div>
      {!data ? (
        <p className="rh-empty">—</p>
      ) : (
        <div className="rh-cleaning-body">
          <div className="rh-cleaning-main">
            {total === 0 ? (
              <span className="rh-metric-caption">{t('home.cleaning.empty')}</span>
            ) : (
              <>
                <span className="rh-metric-number rh-cleaning-number">
                  {done}<span> / {total}</span>
                </span>
                <span className="rh-metric-caption">{t('home.cleaning.done')}</span>
                <div className="rh-clean-progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
                  <span style={{ width: `${(done / total) * 100}%` }} />
                </div>
                <span className="rh-metric-caption">{t('home.cleaning.rule')}</span>
              </>
            )}
          </div>
          <ul className="rh-cleaning-list">
            {data.buildings.map((building) => (
              <li key={building.building_id} className={`rh-cleaning-row rh-cleaning-row--${building.state}`}>
                <strong>{building.address}</strong>
                <span>
                  {t(`home.cleaning.state.${building.state}`)}{building.done_at ? ` · ${formatTime(building.done_at)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
