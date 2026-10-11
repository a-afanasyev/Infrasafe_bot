import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { usePublicElevators, type PublicElevator } from '../../hooks/usePublicElevators'
import { summaryOf } from '../elevators-public/publicElevatorsFilter'
import { isProblemStatus } from '../elevators-public/publicElevatorStyles'
import type { ElevatorStatus } from '../../types/elevators'
import HomeIcon from './HomeIcon'
import type { Lang } from './homeFormat'

// Сколько неработающих лифтов перечислить в карточке; остальные — «и ещё N».
export const MAX_PROBLEMS = 3

const NOT_OK: readonly ElevatorStatus[] = ['not_working', 'under_repair', 'maintenance']

interface ElevatorsCardProps {
  title: string
  lang: Lang
}

// «Лифты» на странице жителей: сводка «N из M работают», счётчики по статусам и
// неработающие лифты. Данные — реестр лифтов (раздел «Лифты» дашборда), тот же
// анонимный эндпоинт, что у табло и страницы /elevators; полный список — там.
export default function ElevatorsCard({ title, lang }: ElevatorsCardProps) {
  const { t } = useTranslation()
  const { data } = usePublicElevators(lang)
  const summary = summaryOf(data)
  const problems: PublicElevator[] = (data?.yards ?? [])
    .flatMap((y) => y.buildings.flatMap((b) => b.elevators))
    .filter((e) => isProblemStatus(e.status))
  const rest = problems.length - MAX_PROBLEMS

  return (
    <section className="rh-card rh-elevators" aria-labelledby="rh-elevators-heading">
      <div className="rh-section-heading">
        <div>
          <h2 id="rh-elevators-heading">{title || t('home.elevators.title')}</h2>
          <p>{t('home.elevators.sub')}</p>
        </div>
        <Link className="rh-small-action" to="/elevators">
          {t('home.elevators.viewAll')}
          <HomeIcon name="arrow" />
        </Link>
      </div>

      {summary.total === 0 ? (
        <p className="rh-empty">{data ? t('home.elevators.empty') : '—'}</p>
      ) : (
        <div className="rh-elevators-body">
          <div className="rh-elevators-main">
            <span className="rh-metric-number rh-elevators-number">
              {summary.working}<span> / {summary.total}</span>
            </span>
            <span className="rh-metric-caption">{t('home.elevators.working')}</span>
            <div className="rh-elevator-chips">
              {NOT_OK.filter((s) => summary[s] > 0).map((s) => (
                <span key={s} className={`rh-elevator-chip rh-elevator-chip--${s}`}>
                  <span className="rh-status-dot" />
                  {t(`elevators.status.${s}`)} — {summary[s]}
                </span>
              ))}
            </div>
          </div>
          <div className="rh-elevator-problems">
            {problems.length === 0 ? (
              <p className="rh-elevators-ok">{t('home.elevators.allWorking')}</p>
            ) : (
              <>
                {problems.slice(0, MAX_PROBLEMS).map((e) => (
                  <div key={e.label} className={`rh-elevator-row rh-elevator-row--${e.status}`}>
                    <strong>{e.label}</strong>
                    <span>{t(`elevators.status.${e.status}`)}</span>
                  </div>
                ))}
                {rest > 0 && <p className="rh-empty">{t('home.elevators.andMore', { count: rest })}</p>}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
