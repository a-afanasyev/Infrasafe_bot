import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PublicBoardData, RequestGroup } from '../../hooks/usePublicBoard'
import HomeIcon from './HomeIcon'
import { MONTH_KEYS, categoryLine } from './homeFormat'

interface RequestsCardProps {
  board: PublicBoardData | undefined
  // Месяц стенки объекта (0–11) — для подписи «Октябрь · общая сводка».
  month: number
}

const IN_PROGRESS = ['В работе', 'Закуп', 'Уточнение']

interface Metric {
  group: RequestGroup
  label: string
  caption: string
  value: number | null
}

// «Обращения по дому»: три счётчика; нажатие на счётчик показывает разбивку
// по категориям внизу карточки, «Все» — общую подпись. Только агрегаты —
// публичный эндпоинт не отдаёт ничего личного.
export default function RequestsCard({ board, month }: RequestsCardProps) {
  const { t } = useTranslation()
  const [selected, setSelected] = useState<RequestGroup | null>(null)
  const counts = board?.status_counts ?? {}
  const loaded = board !== undefined

  const metrics: Metric[] = [
    { group: 'new', label: t('home.newRequests'), caption: t('home.waiting'), value: loaded ? counts['Новая'] ?? 0 : null },
    {
      group: 'in_progress', label: t('home.inProgress'), caption: t('home.withTeam'),
      value: loaded ? IN_PROGRESS.reduce((s, k) => s + (counts[k] ?? 0), 0) : null,
    },
    {
      group: 'completed_month', label: t('home.doneMonth'), caption: t('home.closedRequests'),
      value: loaded ? board?.completed_month ?? null : null,
    },
  ]

  const monthName = t(`home.monthsNominative.${MONTH_KEYS[month]}`)
  const detail = selected
    ? categoryLine(board?.category_counts?.[selected], t) || t('home.summaryEmpty')
    : t('home.summaryAll', { month: monthName })

  return (
    <section className="rh-card rh-requests" aria-labelledby="rh-requests-heading">
      <div className="rh-section-heading">
        <div>
          <h2 id="rh-requests-heading">{t('home.houseRequests')}</h2>
          <p>{t('home.requestsSub')}</p>
        </div>
        <button
          type="button"
          className={selected ? 'rh-small-action' : 'rh-small-action rh-small-action--active'}
          aria-label={t('home.showAll')}
          onClick={() => setSelected(null)}
        >
          {t('home.all')}
          <HomeIcon name="grid" />
        </button>
      </div>
      <div className="rh-metrics" role="group" aria-label={t('home.filter')}>
        {metrics.map((m) => (
          <button
            key={m.group}
            type="button"
            className={`rh-metric rh-metric--${m.group}`}
            aria-pressed={selected === m.group}
            onClick={() => setSelected((s) => (s === m.group ? null : m.group))}
          >
            <span className="rh-metric-label"><span className="rh-status-dot" />{m.label}</span>
            <span className="rh-metric-number">{m.value ?? '—'}</span>
            <span className="rh-metric-caption">{m.caption}</span>
          </button>
        ))}
      </div>
      <div className="rh-request-detail" aria-live="polite">
        <HomeIcon name="info" />
        <span>{detail}</span>
      </div>
    </section>
  )
}
