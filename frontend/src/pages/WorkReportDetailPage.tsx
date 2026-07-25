import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { tCategory } from '../i18n/apiMaps'
import { usePublicWorkReport, publicWorkReportMediaUrl } from '../hooks/usePublicWorkReports'
import { usePageTitle } from '../hooks/usePageTitle'
import EmptyState from '../components/shared/EmptyState'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import WorkReportPhoto from '../components/board/WorkReportPhoto'
import { formatCompletedOn } from '../components/board/formatCompletedOn'

// Публичная страница ОДНОГО отчёта — цель нажатия по миниатюре в блоке на
// табло (WorkReportsModule) и в архиве. Отдельный URL, а не модалка: ссылку
// вида /uk/work-reports/42 можно дать проверяющему органу на конкретную работу.
//
// Здесь показываются ВСЕ фото обеих сторон, а не только первая пара, как на
// миниатюре: смысл страницы — крупный разбор, а не превью.

const photoBoxStyle: React.CSSProperties = {
  aspectRatio: '4 / 3',
  borderRadius: 12,
  overflow: 'hidden',
  background: '#f0ede6',
}
const photoPlaceholderStyle: React.CSSProperties = { fontSize: '0.85rem', padding: 10 }

function PhotoColumn({ ids, reportId, label }: { ids: number[]; reportId: number; label: string }) {
  return (
    <div>
      <div
        style={{
          fontFamily: "'Sora',sans-serif",
          fontWeight: 700,
          fontSize: '1rem',
          marginBottom: 12,
          color: '#1a1a1a',
        }}
      >
        {label}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Пустая сторона у опубликованного отчёта — состояние, которого быть не
            должно (publish требует обе), но рендерим плейсхолдер, а не пустоту:
            «ничего» читалось бы как поломка вёрстки. */}
        {ids.length === 0 ? (
          <WorkReportPhoto
            alt={label}
            boxStyle={photoBoxStyle}
            placeholderStyle={photoPlaceholderStyle}
          />
        ) : (
          ids.map((mediaId) => (
            <WorkReportPhoto
              key={mediaId}
              src={publicWorkReportMediaUrl(reportId, mediaId)}
              alt={label}
              boxStyle={photoBoxStyle}
              placeholderStyle={photoPlaceholderStyle}
            />
          ))
        )}
      </div>
    </div>
  )
}

export default function WorkReportDetailPage() {
  const { t } = useTranslation()
  const { reportId } = useParams<{ reportId: string }>()
  const parsedId = Number(reportId)
  const { data: report, isLoading, isError } = usePublicWorkReport(
    Number.isFinite(parsedId) ? parsedId : undefined,
  )

  usePageTitle(
    report
      ? `${tCategory(report.category_key, t)} — ${report.address}`
      : t('workReportDetail.title'),
  )

  return (
    <div
      style={{
        fontFamily: "'Nunito', sans-serif",
        background: '#f7f5f0',
        color: '#1a1a1a',
        minHeight: '100vh',
      }}
    >
      <header
        style={{
          background: '#fff',
          borderBottom: '1px solid rgba(0,0,0,0.06)',
          padding: '24px 48px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)',
          position: 'sticky',
          top: 0,
          zIndex: 50,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div
          style={{
            fontFamily: "'Sora',sans-serif",
            fontWeight: 700,
            fontSize: '1.4rem',
            letterSpacing: '-0.02em',
          }}
        >
          {t('workReportDetail.title')}
        </div>
        <Link
          to="/resident-board"
          style={{
            fontFamily: "'IBM Plex Mono',monospace",
            fontSize: '0.85rem',
            fontWeight: 700,
            color: '#2563eb',
            textDecoration: 'none',
          }}
        >
          {t('workReportsArchive.backToBoard')}
        </Link>
      </header>

      <div style={{ padding: '32px 48px', maxWidth: 1200, margin: '0 auto' }}>
        {isLoading ? (
          <LoadingSpinner />
        ) : isError || !report ? (
          // 404 приходит и на снятый с публикации отчёт — это ожидаемый ответ,
          // поэтому «не найдено», а не «ошибка сервера».
          <EmptyState icon={'\u{1F4F7}'} title={t('workReportDetail.notFound')} />
        ) : (
          <>
            <div
              style={{
                background: '#fff',
                border: '1px solid rgba(0,0,0,0.06)',
                borderRadius: 16,
                boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)',
                padding: 28,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  flexWrap: 'wrap',
                  marginBottom: 14,
                }}
              >
                <span
                  style={{
                    fontFamily: "'IBM Plex Mono',monospace",
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    padding: '5px 14px',
                    borderRadius: 20,
                    background: '#eff3ff',
                    color: '#2563eb',
                  }}
                >
                  {tCategory(report.category_key, t)}
                </span>
                <span
                  style={{
                    fontFamily: "'IBM Plex Mono',monospace",
                    fontSize: '0.8rem',
                    color: '#9ca3af',
                  }}
                >
                  {formatCompletedOn(report.completed_on)}
                </span>
              </div>

              <h1
                style={{
                  fontFamily: "'Sora',sans-serif",
                  fontSize: '1.5rem',
                  fontWeight: 700,
                  lineHeight: 1.25,
                  margin: '0 0 24px',
                }}
              >
                {report.address}
              </h1>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                  gap: 24,
                }}
              >
                <PhotoColumn
                  ids={report.before}
                  reportId={report.id}
                  label={t('board.workReports.before')}
                />
                <PhotoColumn
                  ids={report.after}
                  reportId={report.id}
                  label={t('board.workReports.after')}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24 }}>
              <Link
                to="/work-reports"
                style={{
                  fontFamily: "'IBM Plex Mono',monospace",
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  color: '#2563eb',
                  textDecoration: 'none',
                }}
              >
                {t('board.workReports.viewAll')}
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
