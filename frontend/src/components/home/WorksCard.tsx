import { useTranslation } from 'react-i18next'
import type { PlannedWorkCfg } from '../../types/boardConfig'
import type { DetailContent } from './DetailDialog'
import HomeIcon from './HomeIcon'
import { timeRange, upcomingWorks, workDateLabel, workDateParts, type Lang } from './homeFormat'

// Сколько ближайших работ помещается в карточку без прокрутки.
export const WORKS_LIMIT = 3

interface WorksCardProps {
  works: PlannedWorkCfg[]
  // Заголовок из редактора витрины; '' → i18n-дефолт.
  title: string
  today: string
  lang: Lang
  onOpen: (content: DetailContent) => void
}

export default function WorksCard({ works, title, today, lang, onOpen }: WorksCardProps) {
  const { t } = useTranslation()
  const loc = (v: { ru: string; uz: string }) => v[lang] || v.ru
  const list = upcomingWorks(works.filter((w) => loc(w.title)), today, WORKS_LIMIT)

  return (
    <section className="rh-card rh-works" aria-labelledby="rh-works-heading">
      <div className="rh-section-heading">
        <div>
          <h2 id="rh-works-heading">{title || t('home.upcomingWorks')}</h2>
          <p>{t('home.worksSub')}</p>
        </div>
        <span className="rh-calendar-icon"><HomeIcon name="calendar" /></span>
      </div>
      <div className="rh-works-list">
        {list.length === 0 && <p className="rh-empty">{t('home.noWorks')}</p>}
        {list.map((w) => {
          const { day, month } = workDateParts(w.date, t)
          const time = timeRange(w.time_from, w.time_to) || t('home.allDay')
          const place = loc(w.place)
          const title = loc(w.title)
          const meta = place ? `${time} · ${place}` : time
          return (
            <button
              key={w.id}
              type="button"
              className="rh-work-row"
              aria-label={`${t('home.workDetails')}: ${title}`}
              onClick={() => onOpen({
                kicker: t('home.plannedWork'),
                title,
                date: [workDateLabel(w, t, lang), place].filter(Boolean).join(' · '),
                body: loc(w.text),
              })}
            >
              <span className="rh-work-date"><b>{day}</b><span>{month}</span></span>
              <span className="rh-work-copy">
                <strong>{title}</strong>
                <span>{meta}</span>
              </span>
              <span className="rh-work-arrow"><HomeIcon name="chevron" /></span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
