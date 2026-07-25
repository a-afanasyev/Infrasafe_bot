import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { tCategory } from '../i18n/apiMaps'
import { usePublicWorkReports, publicWorkReportMediaUrl } from '../hooks/usePublicWorkReports'
import { usePageTitle } from '../hooks/usePageTitle'
import EmptyState from '../components/shared/EmptyState'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import type { PublicWorkReport } from '../types/workReports'

// T12 — public, unauthenticated full archive of all published before/after
// work reports (unlike WorkReportsModule.tsx on the resident board, which
// shows only a capped 6-item preview). This is a NEW, self-contained page:
// cardStyle-ish literals and the photo sub-component below intentionally
// duplicate WorkReportsModule.tsx's shape rather than importing from it — the
// same accepted tradeoff already used between ResidentBoardPage.tsx and
// WorkReportsModule.tsx (cardStyle/headerStyle/titleStyle duplicated there).

// "YYYY-MM-DD" (date-only, per PublicWorkReport.completed_on) → "DD.MM.YYYY".
// Regex, not new Date(dateOnly) — Date parses "YYYY-MM-DD" as UTC midnight,
// which renders as the previous day in timezones behind UTC.
function formatCompletedOn(dateOnly: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateOnly)
  if (!m) return dateOnly
  const [, y, mo, d] = m
  return `${d}.${mo}.${y}`
}

const photoBoxStyle: React.CSSProperties = { aspectRatio: '4 / 3', borderRadius: 10, overflow: 'hidden', background: '#f0ede6' }

interface WorkReportPhotoProps {
  // undefined when the report is (defensively) missing a before/after media
  // id — render the placeholder directly, never pass undefined into
  // publicWorkReportMediaUrl.
  src?: string
  alt: string
}

function WorkReportPhoto({ src, alt }: WorkReportPhotoProps) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) {
    return (
      <div style={{ ...photoBoxStyle, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af', fontSize: '0.75rem', fontWeight: 600, textAlign: 'center', padding: 6 }}>
        {alt}
      </div>
    )
  }
  return (
    <div style={photoBoxStyle}>
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
      />
    </div>
  )
}

function ArchiveCard({ report }: { report: PublicWorkReport }) {
  const { t } = useTranslation()
  const beforeId = report.before[0]
  const afterId = report.after[0]
  return (
    <div style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
        <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: '#eff3ff', color: '#2563eb' }}>
          {tCategory(report.category_key, t)}
        </span>
        <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', color: '#9ca3af', flexShrink: 0 }}>
          {formatCompletedOn(report.completed_on)}
        </span>
      </div>
      <div style={{ fontFamily: "'Sora',sans-serif", fontSize: '0.95rem', fontWeight: 700, color: '#1a1a1a', marginBottom: 14, lineHeight: 1.3 }}>
        {report.address}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <WorkReportPhoto
            src={beforeId != null ? publicWorkReportMediaUrl(report.id, beforeId) : undefined}
            alt={t('board.workReports.before')}
          />
          <div style={{ textAlign: 'center', fontSize: '0.72rem', color: '#9ca3af', marginTop: 6, fontWeight: 600 }}>{t('board.workReports.before')}</div>
        </div>
        <div>
          <WorkReportPhoto
            src={afterId != null ? publicWorkReportMediaUrl(report.id, afterId) : undefined}
            alt={t('board.workReports.after')}
          />
          <div style={{ textAlign: 'center', fontSize: '0.72rem', color: '#9ca3af', marginTop: 6, fontWeight: 600 }}>{t('board.workReports.after')}</div>
        </div>
      </div>
    </div>
  )
}

export default function WorkReportsArchivePage() {
  const { t } = useTranslation()
  usePageTitle(t('workReportsArchive.title'))

  const { data, isLoading, hasNextPage, isFetchingNextPage, fetchNextPage } = usePublicWorkReports()
  const items = data?.pages.flatMap(p => p.items) ?? []

  return (
    <div style={{ fontFamily: "'Nunito', sans-serif", background: '#f7f5f0', color: '#1a1a1a', minHeight: '100vh' }}>
      <header style={{ background: '#fff', borderBottom: '1px solid rgba(0,0,0,0.06)', padding: '24px 48px', boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', position: 'sticky', top: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.4rem', letterSpacing: '-0.02em' }}>
          {t('workReportsArchive.title')}
        </div>
        <Link
          to="/resident-board"
          style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.85rem', fontWeight: 700, color: '#2563eb', textDecoration: 'none' }}
        >
          {t('workReportsArchive.backToBoard')}
        </Link>
      </header>

      <div style={{ padding: '32px 48px', maxWidth: 1600, margin: '0 auto' }}>
        {isLoading ? (
          <LoadingSpinner />
        ) : items.length === 0 ? (
          <EmptyState icon={'\u{1F4F7}'} title={t('workReportsArchive.empty')} />
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20 }}>
              {items.map(report => (
                <ArchiveCard key={report.id} report={report} />
              ))}
            </div>

            {hasNextPage && (
              <div style={{ display: 'flex', justifyContent: 'center', marginTop: 32 }}>
                <button
                  type="button"
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                  style={{
                    fontFamily: "'Sora',sans-serif",
                    fontWeight: 700,
                    fontSize: '0.9rem',
                    padding: '12px 28px',
                    borderRadius: 10,
                    border: 'none',
                    background: 'var(--board-green)',
                    color: '#fff',
                    cursor: isFetchingNextPage ? 'default' : 'pointer',
                    opacity: isFetchingNextPage ? 0.7 : 1,
                  }}
                >
                  {isFetchingNextPage ? t('workReportsArchive.loadingMore') : t('workReportsArchive.loadMore')}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
