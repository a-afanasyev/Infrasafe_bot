import { useTranslation } from 'react-i18next'
import { Link, Navigate, useSearchParams } from 'react-router'
import { usePublicElevators, type PublicLang } from '../hooks/usePublicElevators'
import { usePageTitle } from '../hooks/usePageTitle'
import { isElevatorsEnabled } from '../utils/featureFlags'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import PublicElevatorsSummary from '../components/elevators-public/PublicElevatorsSummary'
import PublicElevatorsFilters from '../components/elevators-public/PublicElevatorsFilters'
import PublicElevatorsList from '../components/elevators-public/PublicElevatorsList'
import {
  applyFilter,
  buildingCounts,
  countByStatus,
  parseFilter,
  serializeFilter,
  summaryOf,
  type PublicElevatorsFilter,
} from '../components/elevators-public/publicElevatorsFilter'
import { cardStyle, formatClock, monoStyle, pillStyle } from '../components/elevators-public/publicElevatorStyles'

// T17 (Р17) — публичная страница «Лифты» (/elevators, без входа): полный список
// к сводке на табло жителей. Рассчитана на ~100 лифтов с телефона: поиск по
// адресу, чипы статуса со счётчиками, селект двора, группы двор → дом → подъезд.
// Состояние фильтров — в URL (?status=&q=&yard=), ссылку можно переслать.
// Данные — тот же хук usePublicElevators (поллинг 60 с). Стиль Resident Board.
// DARK за VITE_ELEVATORS_ENABLED: при выключенном флаге — редирект на табло.

const RESPONSIVE_CSS = `
  .pe-header { padding: 20px 48px; }
  .pe-shell { padding: 24px 48px; }
  .pe-footer { padding: 16px 48px; }
  @media (max-width: 600px) {
    .pe-header { padding: 14px 16px; }
    .pe-shell { padding: 16px 12px; }
    .pe-footer { padding: 12px 16px; }
    .pe-filters { flex-direction: column; }
  }
`

const linkStyle: React.CSSProperties = { ...monoStyle, fontSize: '0.85rem', fontWeight: 700, color: '#2563eb', textDecoration: 'none' }

function NotFound({ onReset }: { onReset: () => void }) {
  const { t } = useTranslation()
  return (
    <div style={{ ...cardStyle, padding: '28px 20px', textAlign: 'center', color: '#6b7280' }}>
      <div style={{ fontSize: '0.95rem', marginBottom: 12 }}>{t('publicElevators.notFound')}</div>
      <button
        type="button"
        onClick={onReset}
        style={{ font: 'inherit', fontWeight: 700, fontSize: '0.85rem', padding: '8px 16px', borderRadius: 10, border: '1px solid rgba(0,0,0,0.12)', background: '#fff', color: '#2563eb', cursor: 'pointer' }}
      >
        {t('publicElevators.resetFilters')}
      </button>
    </div>
  )
}

export default function ResidentElevatorsPage() {
  const { t, i18n } = useTranslation()
  usePageTitle(t('publicElevators.title'))
  const [searchParams, setSearchParams] = useSearchParams()
  const lang: PublicLang = i18n.language?.startsWith('uz') ? 'uz' : 'ru'
  // enabled: при выключенном флаге запрос не уходит — ниже сразу редирект.
  const { data, isLoading, dataUpdatedAt } = usePublicElevators(lang, { enabled: isElevatorsEnabled() })

  if (!isElevatorsEnabled()) return <Navigate to="/resident-board" replace />

  const filter = parseFilter(searchParams)
  const yards = data?.yards ?? []
  const isEmpty = !isLoading && summaryOf(data).total === 0
  // Строка «N из M работают» и чипы — в ОДНОМ масштабе: двор/поиск (чип статуса
  // строку не меняет). Без фильтров совпадает с серверной сводкой.
  const scopedSummary = countByStatus(applyFilter(yards, { ...filter, status: null }))
  const shown = applyFilter(yards, filter)
  const dispatchPhone = data?.dispatch_phone ?? null

  const update = (patch: Partial<PublicElevatorsFilter>) =>
    setSearchParams(serializeFilter({ ...filter, ...patch }), { replace: true })
  const reset = () => setSearchParams(new URLSearchParams(), { replace: true })

  return (
    <div style={{ fontFamily: "'Nunito', sans-serif", background: '#f7f5f0', color: '#1a1a1a', minHeight: '100vh' }}>
      <style>{RESPONSIVE_CSS}</style>

      <header className="pe-header" style={{ background: '#fff', borderBottom: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', position: 'sticky', top: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.4rem', letterSpacing: '-0.02em' }}>
          {t('publicElevators.title')}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {dispatchPhone && (
            <a href={`tel:${dispatchPhone.replace(/[^\d+]/g, '')}`} style={{ ...pillStyle, background: '#eff3ff', color: '#2563eb', textDecoration: 'none' }}>
              {'\u{1F4DE}'} {t('board.elevators.dispatch')}: {dispatchPhone}
            </a>
          )}
          <Link to="/resident-board" style={linkStyle}>{t('publicElevators.backToBoard')}</Link>
        </div>
      </header>

      <div className="pe-shell" style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {isLoading ? (
          <LoadingSpinner />
        ) : isEmpty ? (
          <div style={{ ...cardStyle, padding: '32px 20px', textAlign: 'center', color: '#9ca3af', fontSize: '0.95rem' }}>
            {t('board.elevators.empty')}
          </div>
        ) : (
          <>
            <div style={{ ...cardStyle, padding: '20px 24px' }}>
              <PublicElevatorsSummary summary={scopedSummary} value={filter.status} onChange={(status) => update({ status })} />
            </div>
            <PublicElevatorsFilters filter={filter} yards={yards} onChange={update} />
            {shown.length === 0 ? (
              <NotFound onReset={reset} />
            ) : (
              <PublicElevatorsList yards={shown} counts={buildingCounts(yards)} showYardNames={yards.length > 1} />
            )}
          </>
        )}
      </div>

      {dataUpdatedAt > 0 && (
        <footer className="pe-footer" style={{ textAlign: 'center', color: '#9ca3af', fontSize: '0.82rem' }}>
          {t('publicElevators.updatedAt', { time: formatClock(dataUpdatedAt) })}
        </footer>
      )}
    </div>
  )
}
