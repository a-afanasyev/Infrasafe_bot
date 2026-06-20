import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tCategory } from '../i18n/apiMaps'
import { usePublicBoard } from '../hooks/usePublicBoard'
import { useBoardConfig } from '../hooks/useBoardConfig'
import { defaultBoardConfig } from '../types/boardConfig'
import type { BoardConfigData, LocalizedText } from '../types/boardConfig'
import { usePageTitle } from '../hooks/usePageTitle'

// ── helpers ──────────────────────────────────────────────────────────────────

function formatClock(d: Date) {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatUpdateTime(d: Date) {
  return `${formatClock(d)}:${String(d.getSeconds()).padStart(2, '0')}`
}

// "08:00" → "08", "09:30" → "09:30" — compact for the small day tile.
function hm(t: string) {
  return /:00$/.test(t) ? t.slice(0, 2) : t
}

// ISO → "10.03, 09:00"; falls back to the raw string if unparseable.
function formatPublished(iso: string) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}, ${formatClock(d)}`
}

const CATEGORY_ICONS: Record<string, string> = {
  // Russian keys (web/callcenter) + English keys (bot)
  'Сантехника': '\u{1F527}', 'plumbing': '\u{1F527}',
  'Электрика': '⚡', 'electricity': '⚡',
  'Лифт': '\u{1F6D7}', 'elevator': '\u{1F6D7}',
  'Вентиляция': '\u{1F4A8}', 'ventilation': '\u{1F4A8}',
  'Уборка': '\u{1F9F9}', 'cleaning': '\u{1F9F9}',
  'Отопление': '\u{1F525}', 'heating': '\u{1F525}',
  'Безопасность': '\u{1F512}', 'security': '\u{1F512}',
  'Благоустройство': '\u{1F33F}', 'landscaping': '\u{1F33F}',
  'Ремонт': '\u{1F3D7}️', 'repair': '\u{1F3D7}️',
  'Интернет/ТВ': '\u{1F4E1}', 'internet_tv': '\u{1F4E1}', 'internet': '\u{1F4E1}',
}

// Pipeline stages use API status values (Russian)
const PIPELINE_STATUSES = [
  { status: 'Новая', key: 'new', color: '#2563eb', bg: '#eff3ff' },
  { status: 'В работе', key: 'in_progress', color: '#7c3aed', bg: '#f3f0ff' },
  { status: 'Закуп', key: 'purchase', color: '#d97706', bg: '#fef9e7' },
  { status: 'Уточнение', key: 'clarification', color: '#0891b2', bg: '#ecfeff' },
  { status: 'Выполнена', key: 'executed', color: '#059669', bg: '#ecfdf5' },
  { status: 'Принято', key: 'approved', color: '#16a34a', bg: '#f0fdf4' },
]

const DOT: React.CSSProperties = { display: 'inline-block', width: 6, height: 6, background: 'rgba(255,255,255,0.4)', borderRadius: '50%', margin: '0 32px', verticalAlign: 'middle' }

interface ResidentBoardPageProps {
  // Live preview from the board editor renders with an unsaved draft.
  configOverride?: BoardConfigData
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ResidentBoardPage({ configOverride }: ResidentBoardPageProps) {
  const { t, i18n } = useTranslation()
  // QA-03: иначе document.title оставался от предыдущей страницы.
  // WR-07: в режиме live-preview (configOverride задан из BoardEditorPage) не
  // перетираем заголовок вкладки — иначе показывается «Табло жителей» вместо
  // «Редактор витрины».
  usePageTitle(t('nav.residentBoard'), !configOverride)
  const [now, setNow] = useState(new Date())
  const { data: board } = usePublicBoard()
  const { data: fetchedConfig } = useBoardConfig()

  const config = configOverride ?? fetchedConfig ?? defaultBoardConfig
  const lang: 'ru' | 'uz' = i18n.language?.startsWith('uz') ? 'uz' : 'ru'
  const loc = (lt: LocalizedText) => lt?.[lang] || lt?.ru || ''

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  // Date formatting via i18n
  const dayKeys = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const
  const monthKeys = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'] as const
  const dateLabel = `${t(`days.full.${dayKeys[now.getDay()]}`)}, ${now.getDate()} ${t(`months.${monthKeys[now.getMonth()]}`)} ${now.getFullYear()}`

  // Elapsed time helper — FE-035: takes the tracked `now` so it stays pure in
  // render (no impure Date.now() call; React Compiler no longer flags it).
  function elapsed(iso: string, now: Date) {
    const diff = (now.getTime() - new Date(iso).getTime()) / 1000
    if (diff < 3600) return t('board.elapsed.min', { count: Math.round(diff / 60) })
    if (diff < 86400) return t('board.elapsed.hours', { count: Math.round(diff / 3600) })
    return t('board.elapsed.days', { count: Math.round(diff / 86400) })
  }

  const statusCounts = board?.status_counts ?? {}
  const totalActive = ['Новая', 'В работе', 'Закуп', 'Уточнение'].reduce((s, k) => s + (statusCounts[k] ?? 0), 0)
  const totalDone = ['Выполнена', 'Исполнено', 'Принято'].reduce((s, k) => s + (statusCounts[k] ?? 0), 0)

  const activeRequests = board?.active_requests ?? []

  const todayDow = now.getDay() === 0 ? 6 : now.getDay() - 1

  const avgResH = board?.avg_resolution_hours != null
    ? board.avg_resolution_hours.toFixed(1)
    : '—'

  const effScore = board?.avg_efficiency ?? null
  const satisfactionVal = effScore != null ? (effScore / 20).toFixed(1) : '4.2'
  const satisfactionPct = effScore != null ? Math.round(effScore) : 84
  const starFill = Math.min(5, Math.round(Number(satisfactionVal)))

  // ── Editable content from board config ──────────────────────────────────────
  const dispatchText = `${loc(config.contacts.dispatch_label)}: ${config.contacts.dispatch_phone}`
  const botText = `${loc(config.bot.label)}: @${config.bot.username}`

  // ── Modules ─────────────────────────────────────────────────────────────────
  const cardStyle: React.CSSProperties = { background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }
  const headerStyle: React.CSSProperties = { padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', background: '#f0ede6' }
  const titleStyle: React.CSSProperties = { fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }

  const statsModule = (
    <div key="stats" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16 }}>
      {([
        { icon: '\u{1F4CB}', iconBg: '#eff3ff', label: t('board.stats.activeRequests'),
          render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#2563eb' }}>{totalActive}</span> },
        { icon: '✅', iconBg: '#ecfdf5', label: t('board.stats.completedMonth'),
          render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#059669' }}>{totalDone}</span> },
        { icon: '⏱', iconBg: '#fef9e7', label: t('board.stats.avgResolution'),
          render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#d97706' }}>{avgResH}<span style={{ fontSize: '1rem', color: '#9ca3af' }}>{t('analytics.h')}</span></span> },
        { icon: '\u{1F465}', iconBg: '#f3f0ff', label: t('board.stats.specialistsOnShift'),
          render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#7c3aed' }}>{board?.active_executors ?? '—'}</span> },
      ] as const).map(tile => (
        <div key={tile.label} className="rb-stat-tile" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, padding: '24px 28px', boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', display: 'flex', alignItems: 'center', gap: 20, transition: 'transform 0.2s,box-shadow 0.2s', cursor: 'default' }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: tile.iconBg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.6rem', flexShrink: 0 }}>{tile.icon}</div>
          <div>
            {tile.render()}
            <div style={{ fontSize: '0.85rem', color: '#6b7280', marginTop: 4, fontWeight: 600 }}>{tile.label}</div>
          </div>
        </div>
      ))}
    </div>
  )

  const requestsModule = (
    <div key="requests" style={cardStyle}>
      <div style={{ ...headerStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ ...titleStyle, letterSpacing: '-0.01em' }}>{t('board.sections.currentRequests')}</div>
        <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: '#eff3ff', color: '#2563eb' }}>{t('board.sections.activeCount', { count: totalActive })}</div>
      </div>
      {/* Horizontal scroll wrapper: on narrow viewports (mobile) the 6-status
          pipeline + 6-column grid don't fit. Inner block has min-width so
          users can swipe sideways through all status columns instead of
          getting the rightmost columns clipped. */}
      <div style={{ padding: '20px 0', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
        <div style={{ minWidth: 720, padding: '0 28px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 20 }}>
            {PIPELINE_STATUSES.map((step, i) => (
              <div key={step.status} style={{ display: 'contents' }}>
                <div style={{ flex: 1, textAlign: 'center', padding: '14px 8px', borderRadius: 10, background: step.bg, color: step.color }}>
                  <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '1.4rem', fontWeight: 700, display: 'block', marginBottom: 4 }}>{statusCounts[step.status] ?? 0}</span>
                  <span style={{ fontSize: '0.7rem', fontWeight: 700, opacity: 0.8 }}>{t(`board.pipeline.${step.key}`)}</span>
                </div>
                {i < PIPELINE_STATUSES.length - 1 && <span style={{ color: '#9ca3af', fontSize: '1.2rem', flexShrink: 0 }}>{'→'}</span>}
              </div>
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)' }}>
            {PIPELINE_STATUSES.map((step, i) => {
              const colReqs = activeRequests.filter(r => r.status === step.status)
              return (
                <div key={step.status} style={{ padding: '0 10px', borderRight: i < PIPELINE_STATUSES.length - 1 ? '1px solid rgba(0,0,0,0.07)' : 'none' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {colReqs.length === 0 ? (
                      <div style={{ textAlign: 'center', padding: '14px 4px', color: '#cbd5e1', fontSize: '0.85rem' }}>{'—'}</div>
                    ) : colReqs.map((req) => {
                      const catIcon = CATEGORY_ICONS[req.category] ?? '\u{1F4CB}'
                      return (
                        // FE-037: PublicBoardRequest is anonymized (no id/number),
                        // so the most stable key available is created_at + category.
                        <div key={`${req.created_at}-${req.category}`} className="rb-req-row" style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid rgba(0,0,0,0.06)', borderLeft: `3px solid ${step.color}`, transition: 'background 0.15s', cursor: 'default' }}>
                          <div style={{ fontSize: '0.84rem', fontWeight: 600, color: '#1a1a1a', lineHeight: 1.3 }}>{catIcon} {tCategory(req.category, t)}</div>
                          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.72rem', color: '#9ca3af', marginTop: 4 }}>{elapsed(req.created_at, now)}</div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )

  const announcementsModule = (
    <div key="announcements" style={cardStyle}>
      <div style={{ ...headerStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={titleStyle}>{t('board.sections.announcements')}</div>
        <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: '#fef9e7', color: '#d97706' }}>{t('board.sections.important')}</div>
      </div>
      <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {config.announcements.filter(a => loc(a.title)).map(ann => (
          <div key={ann.id} className="rb-ann" style={{ display: 'flex', gap: 16, padding: '18px 20px', borderRadius: 10, border: '1px solid rgba(0,0,0,0.06)', transition: 'box-shadow 0.2s' }}>
            <div style={{ width: 44, height: 44, borderRadius: 12, background: ann.important ? '#fef2f2' : '#eff3ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.3rem', flexShrink: 0 }}>{ann.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '0.95rem', marginBottom: 4 }}>{loc(ann.title)}</div>
              {loc(ann.text) && <div style={{ fontSize: '0.85rem', color: '#6b7280', lineHeight: 1.5 }}>{loc(ann.text)}</div>}
              <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.72rem', color: '#9ca3af', marginTop: 6 }}>{t('board.sections.published')} {formatPublished(ann.published_at)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )

  const ratingModule = (
    <div key="rating" style={cardStyle}>
      <div style={headerStyle}>
        <div style={titleStyle}>{t('board.sections.residentRating')}</div>
      </div>
      <div style={{ padding: '20px 28px', textAlign: 'center' }}>
        <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 800, fontSize: '3.5rem', color: '#1a6b52', letterSpacing: '-0.04em', lineHeight: 1 }}>{satisfactionVal}</div>
        <div style={{ fontSize: '1.5rem', margin: '8px 0', letterSpacing: 4 }}>{'★'.repeat(starFill)}{'☆'.repeat(5 - starFill)}</div>
        <div style={{ fontSize: '0.85rem', color: '#6b7280', fontWeight: 600 }}>{t('board.sections.efficiencyPeriod')}</div>
        <div style={{ width: '80%', margin: '16px auto 0', height: 8, background: '#f0ede6', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{ height: '100%', borderRadius: 4, background: 'linear-gradient(90deg,#1a6b52,#059669)', width: `${satisfactionPct}%` }} />
        </div>
      </div>
    </div>
  )

  const hoursModule = (
    <div key="hours" style={cardStyle}>
      <div style={headerStyle}>
        <div style={titleStyle}>{t('board.sections.workingHours')}</div>
      </div>
      {/* TWA-17: 7 day cells × time-range labels overflow narrow phone widths
          (≤360px). Wrap the grid (only) in a horizontal-scroll container
          with min-width so users can swipe through the week — same pattern
          as the request pipeline above. Emergency contact + bot text stay
          outside so they don't pick up the horizontal scrollbar. */}
      <div style={{ paddingTop: 20, overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
        <div style={{ minWidth: 560, padding: '0 28px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 8, textAlign: 'center' }}>
            {config.working_hours.map((d, i) => (
              <div key={d.day}>
                <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '0.78rem', color: i === todayDow ? '#1a6b52' : '#6b7280', marginBottom: 6 }}>{t(`days.short.${d.day}`)}</div>
                <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 600, padding: '8px 4px', borderRadius: 8, background: i === todayDow ? '#e8f5ef' : '#f0ede6', color: i === todayDow ? '#1a6b52' : '#1a1a1a', border: `2px solid ${i === todayDow ? '#1a6b52' : 'transparent'}` }}>
                  {d.closed ? '—' : `${hm(d.open)}–${hm(d.close)}`}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div style={{ padding: '0 28px 20px' }}>
        <div style={{ textAlign: 'center', marginTop: 16, padding: 12, background: '#fef2f2', borderRadius: 10, fontSize: '0.85rem', fontWeight: 600, color: '#dc2626' }}>
          {'\u{1F4DE}'} {loc(config.contacts.emergency)}
        </div>
        <div style={{ textAlign: 'center', marginTop: 10, fontSize: '0.82rem', color: '#6b7280' }}>
          {'\u{1F4F1}'} {botText}
        </div>
      </div>
    </div>
  )

  const MODULES: Record<string, React.ReactNode> = {
    stats: statsModule,
    requests: requestsModule,
    announcements: announcementsModule,
    rating: ratingModule,
    hours: hoursModule,
  }

  return (
    <div style={{ fontFamily: "'Nunito', sans-serif", background: '#f7f5f0', color: '#1a1a1a', minHeight: '100vh', overflowX: 'hidden' }}>

      <style>{`
        /* FE-040: @import for Sora/Nunito/IBM Plex Mono moved to index.html
           (it re-injected and render-blocked on every render here). */
        @keyframes ticker { 0% { transform: translateX(100vw); } 100% { transform: translateX(-100%); } }
        @keyframes rb-pulse { 0%,100% { opacity:1; box-shadow:0 0 0 0 rgba(5,150,105,0.4); } 50% { opacity:.7; box-shadow:0 0 0 6px rgba(5,150,105,0); } }
        .rb-req-row:hover { background: #f0ede6 !important; }
        .rb-ann:hover { box-shadow: 0 4px 24px rgba(0,0,0,0.08) !important; }
        .rb-stat-tile:hover { transform: translateY(-2px); box-shadow: 0 4px 24px rgba(0,0,0,0.08) !important; }
      `}</style>

      {/* Ticker */}
      <div style={{ background: '#1a6b52', color: '#fff', padding: '10px 0', overflow: 'hidden', whiteSpace: 'nowrap' }}>
        <span style={{ display: 'inline-block', animation: 'ticker 34s linear infinite', fontWeight: 600, fontSize: '0.9rem', letterSpacing: '0.02em' }}>
          {'\u{1F4CB}'} {t('board.ticker.newRequests')}
          <span style={DOT} />
          {'\u{1F527}'} {t('board.ticker.specialistsWorking', { count: board?.active_executors ?? '…' })}
          <span style={DOT} />
          {'✅'} {t('board.ticker.completedMonth', { count: totalDone })}
          <span style={DOT} />
          {'\u{1F4DE}'} {dispatchText}
          <span style={DOT} />
          {'\u{1F4F1}'} {botText}
          <span style={DOT} />
        </span>
      </div>

      {/* Header */}
      <header style={{ background: '#fff', borderBottom: '1px solid rgba(0,0,0,0.06)', padding: '24px 48px', display: 'flex', alignItems: 'center', gap: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', position: 'sticky', top: 0, zIndex: 50 }}>
        <div style={{ width: 52, height: 52, background: '#1a6b52', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Sora',sans-serif", fontWeight: 800, fontSize: '1.3rem', color: '#fff', flexShrink: 0 }}>{'УК'}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.4rem', color: '#1a1a1a', letterSpacing: '-0.02em' }}>{loc(config.org.name)}</div>
          <div style={{ fontSize: '0.85rem', color: '#9ca3af', marginTop: 2 }}>{loc(config.org.subtitle)}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', color: '#1a1a1a', letterSpacing: '-0.02em', lineHeight: 1 }}>{formatClock(now)}</div>
          <div style={{ fontSize: '0.85rem', color: '#6b7280', marginTop: 4 }}>{dateLabel}</div>
        </div>
      </header>

      {/* Modules — rendered in the order defined by board config layout */}
      <div style={{ padding: '32px 48px', display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1600, margin: '0 auto' }}>
        {config.layout
          .filter(item => item.visible && MODULES[item.id])
          .map(item => MODULES[item.id])}
      </div>

      {/* Footer */}
      <footer style={{ padding: '20px 48px', textAlign: 'center', color: '#9ca3af', fontSize: '0.82rem', borderTop: '1px solid rgba(0,0,0,0.06)', background: '#fff' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#059669', display: 'inline-block', animation: 'rb-pulse 2s ease-in-out infinite' }} />
          {t('board.footer.realtime', { time: formatUpdateTime(now) })}
        </span>
      </footer>
    </div>
  )
}
