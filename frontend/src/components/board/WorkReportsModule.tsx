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

// Fallback, если конфиг ещё не загрузился — совпадает с бэкендовым дефолтом
// WorkReportsCfg.limit. Реальное значение приходит props'ом из
// ResidentBoardPage (у него уже есть board-config, в т.ч. configOverride
// редактора витрины).
const DEFAULT_MAX_CARDS = 6

const cardStyle: React.CSSProperties = { background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }
const headerStyle: React.CSSProperties = { padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', background: '#f0ede6' }
const titleStyle: React.CSSProperties = { fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }

// Миниатюра: пара «до|после» в одной плитке — смысл отчёта читается без
// нажатия, это и есть «визуальный ряд». Меньше, чем на странице отчёта: здесь
// превью, а разбор — по ссылке.
const photoBoxStyle: React.CSSProperties = { aspectRatio: '1 / 1', borderRadius: 6, overflow: 'hidden', background: '#f0ede6' }
const photoPlaceholderStyle: React.CSSProperties = { fontSize: '0.6rem', padding: 2 }

function ReportThumb({ report, t }: { report: PublicWorkReport; t: TFunction }) {
  const beforeId = report.before[0]
  const afterId = report.after[0]
  return (
    // Плитка целиком — ссылка на страницу отчёта: табло часто висит на
    // телевизоре/тач-панели, и мелкая кликабельная зона там неудобна.
    <Link
      to={`/work-reports/${report.id}`}
      style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
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
      {/* Подписи «До/После» — как на странице архива: пара без подписей
          читается неоднозначно, особенно когда «до» и «после» похожи. */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginTop: 3 }}>
        <span style={{ textAlign: 'center', fontSize: '0.62rem', color: '#9ca3af', fontWeight: 600 }}>
          {t('board.workReports.before')}
        </span>
        <span style={{ textAlign: 'center', fontSize: '0.62rem', color: '#9ca3af', fontWeight: 600 }}>
          {t('board.workReports.after')}
        </span>
      </div>
      <div style={{ marginTop: 6, display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.66rem', fontWeight: 700, color: '#2563eb' }}>
          {tCategory(report.category_key, t)}
        </span>
        <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.62rem', color: '#9ca3af' }}>
          {formatCompletedOn(report.completed_on)}
        </span>
      </div>
      <div style={{ fontSize: '0.74rem', fontWeight: 600, color: '#1a1a1a', lineHeight: 1.25 }}>
        {report.address}
      </div>
    </Link>
  )
}

export interface WorkReportsModuleProps {
  // WorkReportsCfg.limit — сколько карточек показывать на табло (1..24,
  // валидируется бэкендом). undefined, пока board-config не загрузился.
  limit?: number
  // WorkReportsCfg.title, уже локализованный вызывающим. Пустая строка =
  // менеджер не задал заголовок → падаем на i18n-дефолт.
  title?: string
}

// Ленту читает сам (как остальные модули табло), а настройки получает
// props'ами — их владелец ResidentBoardPage, у которого board-config уже есть.
export default function WorkReportsModule({ limit, title }: WorkReportsModuleProps = {}) {
  const { t } = useTranslation()
  const { data } = usePublicWorkReports()
  const maxCards = limit && limit > 0 ? limit : DEFAULT_MAX_CARDS
  const items = (data?.pages[0]?.items ?? []).slice(0, maxCards)

  // Плановое поведение (не лоадер-скелетон): пустой список (включая ещё не
  // разрешившийся запрос) → секция не рендерится вовсе.
  if (items.length === 0) return null

  return (
    <div style={cardStyle}>
      <div style={{ ...headerStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={titleStyle}>{title || t('board.sections.workReports')}</div>
        <Link
          to="/work-reports"
          style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 700, color: '#2563eb', textDecoration: 'none' }}
        >
          {t('board.workReports.viewAll')}
        </Link>
      </div>
      {/* auto-FILL, а не auto-fit: при 6 плитках auto-fit растягивал их на всю
          ширину и один «сирота» уезжал во второй ряд разной величины. */}
      <div style={{ padding: '20px 28px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 18 }}>
        {items.map(report => (
          <ReportThumb key={report.id} report={report} t={t} />
        ))}
      </div>
    </div>
  )
}
