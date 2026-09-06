import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { usePublicElevators, type PublicElevator, type PublicElevatorYard, type PublicLang } from '../../hooks/usePublicElevators'
import PublicElevatorsSummary from '../elevators-public/PublicElevatorsSummary'
import { StatusPill } from '../elevators-public/PublicElevatorRow'
import { summaryOf } from '../elevators-public/publicElevatorsFilter'
import {
  cardStyle,
  formatSinceShort,
  headerStyle,
  isProblemStatus,
  monoStyle,
  pillStyle,
  statusStyle,
  titleStyle,
} from '../elevators-public/publicElevatorStyles'

// T17 (Р17) — модуль табло жителей стал СВОДКОЙ: «84 из 100 работают», чипы со
// счётчиками, до MAX_PROBLEM_ROWS проблемных лифтов и ссылка «Все лифты →» на
// публичную страницу /elevators (полный список; при 100 лифтах список на табло
// неудобен). Пустой ответ НЕ прячет модуль: превью в редакторе витрины должно
// быть видно — показываем заглушку.

const MAX_PROBLEM_ROWS = 5

// Проблемные (not_working/under_repair) в порядке ответа: двор → дом → подъезд → номер.
function problemElevators(yards: PublicElevatorYard[]): PublicElevator[] {
  return yards.flatMap((y) => y.buildings.flatMap((b) => b.elevators.filter((e) => isProblemStatus(e.status))))
}

function ProblemRow({ e }: { e: PublicElevator }) {
  const { t } = useTranslation()
  return (
    <div
      data-testid="elevator-problem-row"
      style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.06)', borderLeft: `3px solid ${statusStyle(e.status).color}` }}
    >
      <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#1a1a1a', flex: '1 1 auto', minWidth: 0 }}>{e.label}</span>{' '}
      <StatusPill status={e.status} />
      {e.status_since && (
        <>
          {' '}
          <span style={{ ...monoStyle, fontSize: '0.72rem', color: '#9ca3af' }}>
            {t('board.elevators.since', { date: formatSinceShort(e.status_since) })}
          </span>
        </>
      )}
    </div>
  )
}

function ProblemList({ problems }: { problems: PublicElevator[] }) {
  const { t } = useTranslation()
  if (problems.length === 0) {
    return (
      <div style={{ fontSize: '0.9rem', fontWeight: 700, color: statusStyle('working').color }}>
        {t('board.elevators.allWorking')}
      </div>
    )
  }
  const shown = problems.slice(0, MAX_PROBLEM_ROWS)
  const rest = problems.length - shown.length
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {shown.map((e) => (
        <ProblemRow key={e.label} e={e} />
      ))}
      {rest > 0 && (
        <div style={{ fontSize: '0.82rem', color: '#6b7280', paddingLeft: 12 }}>{t('board.elevators.andMore', { count: rest })}</div>
      )}
    </div>
  )
}

export interface ElevatorsBoardModuleProps {
  // ElevatorsCfg.title, уже локализованный вызывающим; пусто → i18n-дефолт.
  title?: string
}

// Данные читает сам (как остальные модули табло); заголовок — props'ом от
// ResidentBoardPage, у которого board-config (и configOverride редактора) уже есть.
export default function ElevatorsBoardModule({ title }: ElevatorsBoardModuleProps = {}) {
  const { t, i18n } = useTranslation()
  const lang: PublicLang = i18n.language?.startsWith('uz') ? 'uz' : 'ru'
  const { data } = usePublicElevators(lang)
  const summary = summaryOf(data)
  const dispatchPhone = data?.dispatch_phone ?? null
  const isEmpty = summary.total === 0

  return (
    <div style={cardStyle}>
      <div style={{ ...headerStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={titleStyle}>{title || t('board.sections.elevators')}</div>
        {dispatchPhone && (
          <div style={{ ...pillStyle, background: '#eff3ff', color: '#2563eb' }}>
            {'\u{1F4DE}'} {t('board.elevators.dispatch')}: {dispatchPhone}
          </div>
        )}
      </div>
      <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        {isEmpty ? (
          <div style={{ textAlign: 'center', padding: '14px 4px', color: '#9ca3af', fontSize: '0.9rem' }}>
            {t('board.elevators.empty')}
          </div>
        ) : (
          <>
            <PublicElevatorsSummary summary={summary} hideZero />
            <ProblemList problems={problemElevators(data?.yards ?? [])} />
            <div>
              {/* Роутер с base /uk — Link сам подставит basename, как соседние публичные ссылки табло. */}
              <Link to="/elevators" style={{ ...monoStyle, fontSize: '0.85rem', fontWeight: 700, color: '#2563eb', textDecoration: 'none' }}>
                {t('board.elevators.viewAll')}
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
