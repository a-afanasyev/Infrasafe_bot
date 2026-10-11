import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { tCategory } from '../../i18n/apiMaps'
import { publicWorkReportMediaUrl, usePublicWorkReports } from '../../hooks/usePublicWorkReports'
import type { PublicWorkReport } from '../../types/workReports'
import WorkReportPhoto from '../board/WorkReportPhoto'
import { formatCompletedOn } from '../board/formatCompletedOn'
import HomeIcon from './HomeIcon'

// Сколько свежих отчётов показать в карточке; архив целиком — /work-reports.
export const REPORTS_LIMIT = 3

const PHOTO_BOX: React.CSSProperties = { aspectRatio: '1 / 1', borderRadius: 8, overflow: 'hidden', background: '#f2f5ee' }
const PHOTO_PLACEHOLDER: React.CSSProperties = { fontSize: '0.6rem', padding: 2 }

interface WorkReportsCardProps {
  title: string
}

function ReportTile({ report }: { report: PublicWorkReport }) {
  const { t } = useTranslation()
  const photo = (id: number | undefined, label: string) => (
    <figure>
      <WorkReportPhoto
        src={id != null ? publicWorkReportMediaUrl(report.id, id) : undefined}
        alt={label}
        boxStyle={PHOTO_BOX}
        placeholderStyle={PHOTO_PLACEHOLDER}
        emptyLabel={t('board.workReports.noPhoto')}
      />
      <figcaption>{label}</figcaption>
    </figure>
  )
  return (
    <Link className="rh-report" to={`/work-reports/${report.id}`}>
      <span className="rh-report-photos">
        {photo(report.before[0], t('board.workReports.before'))}
        {photo(report.after[0], t('board.workReports.after'))}
      </span>
      <span className="rh-report-meta">
        <strong>{tCategory(report.category_key, t)}</strong>
        <span>{formatCompletedOn(report.completed_on)} · {report.address}</span>
      </span>
    </Link>
  )
}

// «Отчёты о работах»: свежие опубликованные пары «до/после». Публикует их
// менеджер в разделе «Отчёты о работах» дашборда (модерация или автопубликация).
export default function WorkReportsCard({ title }: WorkReportsCardProps) {
  const { t } = useTranslation()
  const { data } = usePublicWorkReports()
  const items = (data?.pages[0]?.items ?? []).slice(0, REPORTS_LIMIT)

  return (
    <section className="rh-card rh-reports" aria-labelledby="rh-reports-heading">
      <div className="rh-section-heading">
        <div>
          <h2 id="rh-reports-heading">{title || t('home.workReports.title')}</h2>
          <p>{t('home.workReports.sub')}</p>
        </div>
        <Link className="rh-small-action" to="/work-reports">
          {t('home.workReports.viewAll')}
          <HomeIcon name="arrow" />
        </Link>
      </div>
      {items.length === 0 ? (
        <p className="rh-empty">{data ? t('home.workReports.empty') : '—'}</p>
      ) : (
        <div className="rh-reports-list">
          {items.map((r) => <ReportTile key={r.id} report={r} />)}
        </div>
      )}
    </section>
  )
}
