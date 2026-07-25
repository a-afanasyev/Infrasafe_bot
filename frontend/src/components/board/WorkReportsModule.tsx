import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { tCategory } from '../../i18n/apiMaps'
import { usePublicWorkReports, publicWorkReportMediaUrl } from '../../hooks/usePublicWorkReports'
import WorkReportPhoto from './WorkReportPhoto'
import { formatCompletedOn } from './formatCompletedOn'
import type { PublicWorkReport } from '../../types/workReports'

// T10 — public resident-board widget: compact preview of recently-published
// before/after photo reports. First module extracted out of
// ResidentBoardPage.tsx into its own file (that file is already 354 lines and
// shouldn't grow further) — so cardStyle/headerStyle/titleStyle below are a
// deliberate, small duplication of the literal values defined there (not
// exported from that file, can't import them). WorkReportPhoto and
// formatCompletedOn, by contrast, are shared with WorkReportsArchivePage.tsx
// via WorkReportPhoto.tsx/formatCompletedOn.ts — see those files' header
// comments for why.

// Matches the backend's WorkReportsCfg.limit DEFAULT (6). Not wired to the
// manager-configurable value here — that would require pulling in
// useBoardConfig() for one field, out of scope for this task.
const MAX_CARDS = 6

const cardStyle: React.CSSProperties = { background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }
const headerStyle: React.CSSProperties = { padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', background: '#f0ede6' }
const titleStyle: React.CSSProperties = { fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }

const photoBoxStyle: React.CSSProperties = { aspectRatio: '4 / 3', borderRadius: 8, overflow: 'hidden', background: '#f0ede6' }
const photoPlaceholderStyle: React.CSSProperties = { fontSize: '0.72rem', padding: 4 }

function ReportCard({ report, t }: { report: PublicWorkReport; t: TFunction }) {
  const beforeId = report.before[0]
  const afterId = report.after[0]
  return (
    <div style={{ border: '1px solid rgba(0,0,0,0.06)', borderRadius: 10, padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
        <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.72rem', fontWeight: 700, padding: '4px 10px', borderRadius: 20, background: '#eff3ff', color: '#2563eb' }}>
          {tCategory(report.category_key, t)}
        </span>
        <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.72rem', color: '#9ca3af', flexShrink: 0 }}>
          {formatCompletedOn(report.completed_on)}
        </span>
      </div>
      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#1a1a1a', marginBottom: 10, lineHeight: 1.3 }}>
        {report.address}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <WorkReportPhoto
          src={beforeId != null ? publicWorkReportMediaUrl(report.id, beforeId) : undefined}
          alt={t('board.workReports.before')}
          boxStyle={photoBoxStyle}
          placeholderStyle={photoPlaceholderStyle}
        />
        <WorkReportPhoto
          src={afterId != null ? publicWorkReportMediaUrl(report.id, afterId) : undefined}
          alt={t('board.workReports.after')}
          boxStyle={photoBoxStyle}
          placeholderStyle={photoPlaceholderStyle}
        />
      </div>
    </div>
  )
}

// Self-contained module: no props, reads its own data — matches how the
// other resident-board modules read useBoardConfig()/usePublicBoard()
// internally rather than receiving data via props. A later task wires this
// into ResidentBoardPage's module registry.
export default function WorkReportsModule() {
  const { t } = useTranslation()
  const { data } = usePublicWorkReports()
  const items = (data?.pages[0]?.items ?? []).slice(0, MAX_CARDS)

  // Плановое поведение (не лоадер-скелетон): пустой список (включая ещё не
  // разрешившийся запрос) → секция не рендерится вовсе.
  if (items.length === 0) return null

  return (
    <div style={cardStyle}>
      <div style={{ ...headerStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={titleStyle}>{t('board.sections.workReports')}</div>
        <Link
          to="/work-reports"
          style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 700, color: '#2563eb', textDecoration: 'none' }}
        >
          {t('board.workReports.viewAll')}
        </Link>
      </div>
      <div style={{ padding: '20px 28px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
        {items.map(report => (
          <ReportCard key={report.id} report={report} t={t} />
        ))}
      </div>
    </div>
  )
}
