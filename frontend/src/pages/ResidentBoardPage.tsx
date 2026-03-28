import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tCategory } from '../i18n/apiMaps'
import { useKanban } from '../hooks/useKanban'
import { useShiftStats, useRequestStats } from '../hooks/useAnalytics'

// ── helpers ──────────────────────────────────────────────────────────────────

function formatClock(d: Date) {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatUpdateTime(d: Date) {
  return `${formatClock(d)}:${String(d.getSeconds()).padStart(2, '0')}`
}

const CATEGORY_ICONS: Record<string, string> = {
  '\u0421\u0430\u043D\u0442\u0435\u0445\u043D\u0438\u043A\u0430': '\u{1F527}',
  '\u042D\u043B\u0435\u043A\u0442\u0440\u0438\u043A\u0430': '\u26A1',
  '\u041B\u0438\u0444\u0442': '\u{1F6D7}',
  '\u0412\u0435\u043D\u0442\u0438\u043B\u044F\u0446\u0438\u044F': '\u{1F4A8}',
  '\u0423\u0431\u043E\u0440\u043A\u0430': '\u{1F9F9}',
  '\u041E\u0442\u043E\u043F\u043B\u0435\u043D\u0438\u0435': '\u{1F525}',
  '\u0411\u0435\u0437\u043E\u043F\u0430\u0441\u043D\u043E\u0441\u0442\u044C': '\u{1F512}',
  '\u0411\u043B\u0430\u0433\u043E\u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u043E': '\u{1F33F}',
  '\u0420\u0435\u043C\u043E\u043D\u0442': '\u{1F3D7}\uFE0F',
}

// Pipeline stages use API status values (Russian)
const PIPELINE_STATUSES = [
  { status: '\u041D\u043E\u0432\u0430\u044F', key: 'new', color: '#2563eb', bg: '#eff3ff' },
  { status: '\u0412 \u0440\u0430\u0431\u043E\u0442\u0435', key: 'in_progress', color: '#7c3aed', bg: '#f3f0ff' },
  { status: '\u0417\u0430\u043A\u0443\u043F', key: 'purchase', color: '#d97706', bg: '#fef9e7' },
  { status: '\u0423\u0442\u043E\u0447\u043D\u0435\u043D\u0438\u0435', key: 'clarification', color: '#0891b2', bg: '#ecfeff' },
  { status: '\u0412\u044B\u043F\u043E\u043B\u043D\u0435\u043D\u0430', key: 'executed', color: '#059669', bg: '#ecfdf5' },
  { status: '\u041F\u0440\u0438\u043D\u044F\u0442\u043E', key: 'approved', color: '#16a34a', bg: '#f0fdf4' },
]

const STATUS_STYLE: Record<string, { color: string; bg: string; key: string }> = {
  '\u041D\u043E\u0432\u0430\u044F': { color: '#2563eb', bg: '#eff3ff', key: 'new' },
  '\u0412 \u0440\u0430\u0431\u043E\u0442\u0435': { color: '#7c3aed', bg: '#f3f0ff', key: 'in_progress' },
  '\u0417\u0430\u043A\u0443\u043F': { color: '#d97706', bg: '#fef9e7', key: 'purchase' },
  '\u0423\u0442\u043E\u0447\u043D\u0435\u043D\u0438\u0435': { color: '#0891b2', bg: '#ecfeff', key: 'clarification' },
  '\u0412\u044B\u043F\u043E\u043B\u043D\u0435\u043D\u0430': { color: '#059669', bg: '#ecfdf5', key: 'executed' },
  '\u0418\u0441\u043F\u043E\u043B\u043D\u0435\u043D\u043E': { color: '#059669', bg: '#ecfdf5', key: 'executed' },
  '\u041F\u0440\u0438\u043D\u044F\u0442\u043E': { color: '#16a34a', bg: '#f0fdf4', key: 'approved' },
}

const DOT: React.CSSProperties = { display: 'inline-block', width: 6, height: 6, background: 'rgba(255,255,255,0.4)', borderRadius: '50%', margin: '0 32px', verticalAlign: 'middle' }

// ── Component ─────────────────────────────────────────────────────────────────

export default function ResidentBoardPage() {
  const { t } = useTranslation()
  const [now, setNow] = useState(new Date())
  const { columns } = useKanban()
  const { data: shiftStats } = useShiftStats('7d')
  const { data: reqStats } = useRequestStats('30d')

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  // Date formatting via i18n
  const dayKeys = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const
  const monthKeys = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'] as const
  const dateLabel = `${t(`days.full.${dayKeys[now.getDay()]}`)}, ${now.getDate()} ${t(`months.${monthKeys[now.getMonth()]}`)} ${now.getFullYear()}`

  // Elapsed time helper
  function elapsed(iso: string) {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000
    if (diff < 3600) return t('board.elapsed.min', { count: Math.round(diff / 60) })
    if (diff < 86400) return t('board.elapsed.hours', { count: Math.round(diff / 3600) })
    return t('board.elapsed.days', { count: Math.round(diff / 86400) })
  }

  const colMap = Object.fromEntries(columns.map(c => [c.status, c]))
  const totalActive = ['\u041D\u043E\u0432\u0430\u044F', '\u0412 \u0440\u0430\u0431\u043E\u0442\u0435', '\u0417\u0430\u043A\u0443\u043F', '\u0423\u0442\u043E\u0447\u043D\u0435\u043D\u0438\u0435'].reduce((s, k) => s + (colMap[k]?.count ?? 0), 0)
  const totalDone = ['\u0412\u044B\u043F\u043E\u043B\u043D\u0435\u043D\u0430', '\u0418\u0441\u043F\u043E\u043B\u043D\u0435\u043D\u043E', '\u041F\u0440\u0438\u043D\u044F\u0442\u043E'].reduce((s, k) => s + (colMap[k]?.count ?? 0), 0)

  const activeRequests = ['\u041D\u043E\u0432\u0430\u044F', '\u0412 \u0440\u0430\u0431\u043E\u0442\u0435', '\u0417\u0430\u043A\u0443\u043F', '\u0423\u0442\u043E\u0447\u043D\u0435\u043D\u0438\u0435', '\u0412\u044B\u043F\u043E\u043B\u043D\u0435\u043D\u0430']
    .flatMap(s => colMap[s]?.requests ?? [])
    .slice(0, 8)

  const todayDow = now.getDay() === 0 ? 6 : now.getDay() - 1

  const avgResH = reqStats?.avg_resolution_hours != null
    ? reqStats.avg_resolution_hours.toFixed(1)
    : '—'

  const effScore = shiftStats?.avg_efficiency ?? null
  const satisfactionVal = effScore != null ? (effScore / 20).toFixed(1) : '4.2'
  const satisfactionPct = effScore != null ? Math.round(effScore) : 84
  const starFill = Math.min(5, Math.round(Number(satisfactionVal)))

  // Work hours with i18n day abbreviations
  const dayShortKeys = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const
  const WORK_HOURS = dayShortKeys.map((key, i) => ({
    day: t(`days.short.${key}`),
    hours: i < 5 ? '08-20' : i === 5 ? '09-17' : '10-16',
  }))

  // Announcements (static content, kept in component)
  const ANNOUNCEMENTS = [
    { icon: '\u26A0\uFE0F', iconBg: '#fef2f2', title: t('board.ticker.plannedWorks').split(':')[0] ?? '', text: t('board.ticker.plannedWorks').includes(':') ? t('board.ticker.plannedWorks').split(':').slice(1).join(':').trim() : '', time: '10.03, 09:00' },
    { icon: '\u{1F4E2}', iconBg: '#eff3ff', title: t('board.sections.announcements'), text: '', time: '09.03, 14:30' },
    { icon: '\u{1F33F}', iconBg: '#ecfdf5', title: '', text: '', time: '08.03, 11:00' },
  ]

  return (
    <div style={{ fontFamily: "'Nunito', sans-serif", background: '#f7f5f0', color: '#1a1a1a', minHeight: '100vh', overflowX: 'hidden' }}>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=Nunito:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
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
          {'\u{1F527}'} {t('board.ticker.specialistsWorking', { count: shiftStats?.active_executors ?? '\u2026' })}
          <span style={DOT} />
          {'\u2705'} {t('board.ticker.completedMonth', { count: totalDone })}
          <span style={DOT} />
          {'\u26A0\uFE0F'} {t('board.ticker.plannedWorks')}
          <span style={DOT} />
          {'\u{1F4DE}'} {t('board.ticker.dispatch')}
          <span style={DOT} />
          {'\u{1F4F1}'} {t('board.ticker.telegramBot')}
          <span style={DOT} />
        </span>
      </div>

      {/* Header */}
      <header style={{ background: '#fff', borderBottom: '1px solid rgba(0,0,0,0.06)', padding: '24px 48px', display: 'flex', alignItems: 'center', gap: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', position: 'sticky', top: 0, zIndex: 50 }}>
        <div style={{ width: 52, height: 52, background: '#1a6b52', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Sora',sans-serif", fontWeight: 800, fontSize: '1.3rem', color: '#fff', flexShrink: 0 }}>{'\u0423\u041A'}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.4rem', color: '#1a1a1a', letterSpacing: '-0.02em' }}>{t('board.header.title')}</div>
          <div style={{ fontSize: '0.85rem', color: '#9ca3af', marginTop: 2 }}>{t('board.header.subtitle')}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', color: '#1a1a1a', letterSpacing: '-0.02em', lineHeight: 1 }}>{formatClock(now)}</div>
          <div style={{ fontSize: '0.85rem', color: '#6b7280', marginTop: 4 }}>{dateLabel}</div>
        </div>
      </header>

      {/* Main grid */}
      <div style={{ padding: '32px 48px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, maxWidth: 1600, margin: '0 auto' }}>

        {/* Stats Banner */}
        <div style={{ gridColumn: '1/-1', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16 }}>
          {([
            { icon: '\u{1F4CB}', iconBg: '#eff3ff', valColor: '#2563eb', label: t('board.stats.activeRequests'),
              render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#2563eb' }}>{totalActive}</span> },
            { icon: '\u2705', iconBg: '#ecfdf5', valColor: '#059669', label: t('board.stats.completedMonth'),
              render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#059669' }}>{totalDone}</span> },
            { icon: '\u23F1', iconBg: '#fef9e7', valColor: '#d97706', label: t('board.stats.avgResolution'),
              render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#d97706' }}>{avgResH}<span style={{ fontSize: '1rem', color: '#9ca3af' }}>{t('analytics.h')}</span></span> },
            { icon: '\u{1F465}', iconBg: '#f3f0ff', valColor: '#7c3aed', label: t('board.stats.specialistsOnShift'),
              render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#7c3aed' }}>{shiftStats?.active_executors ?? '—'}</span> },
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

        {/* Active Requests -- full width */}
        <div style={{ gridColumn: '1/-1', background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
          <div style={{ padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#f0ede6' }}>
            <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem', letterSpacing: '-0.01em' }}>{t('board.sections.currentRequests')}</div>
            <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: '#eff3ff', color: '#2563eb' }}>{t('board.sections.activeCount', { count: totalActive })}</div>
          </div>
          <div style={{ padding: '20px 28px' }}>
            {/* Pipeline */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 20 }}>
              {PIPELINE_STATUSES.map((step, i) => (
                <div key={step.status} style={{ display: 'contents' }}>
                  <div style={{ flex: 1, textAlign: 'center', padding: '14px 8px', borderRadius: 10, background: step.bg, color: step.color }}>
                    <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '1.4rem', fontWeight: 700, display: 'block', marginBottom: 4 }}>{colMap[step.status]?.count ?? 0}</span>
                    <span style={{ fontSize: '0.7rem', fontWeight: 700, opacity: 0.8 }}>{t(`board.pipeline.${step.key}`)}</span>
                  </div>
                  {i < PIPELINE_STATUSES.length - 1 && <span style={{ color: '#9ca3af', fontSize: '1.2rem', flexShrink: 0 }}>{'\u2192'}</span>}
                </div>
              ))}
            </div>

            {/* Request rows */}
            {activeRequests.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: '0.9rem' }}>{t('board.sections.noActiveRequests')}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {activeRequests.map(req => {
                  const ss = STATUS_STYLE[req.status] ?? { color: '#6b7280', bg: '#f3f4f6', key: 'new' }
                  const catIcon = CATEGORY_ICONS[req.category] ?? '\u{1F4CB}'
                  const descText = req.description
                    ? (req.description.length > 55 ? req.description.slice(0, 55) + '\u2026' : req.description)
                    : req.category
                  return (
                    <div key={req.request_number} className="rb-req-row" style={{ display: 'grid', gridTemplateColumns: '110px 1fr 150px 90px', gap: 16, alignItems: 'center', padding: '14px 18px', borderRadius: 10, border: '1px solid rgba(0,0,0,0.06)', transition: 'background 0.15s', cursor: 'default' }}>
                      <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '0.88rem', color: '#1a6b52' }}>#{req.request_number}</div>
                      <div>
                        <div style={{ fontSize: '0.93rem', fontWeight: 500, color: '#1a1a1a' }}>{descText}</div>
                        <div style={{ fontSize: '0.78rem', color: '#9ca3af', marginTop: 2 }}>{catIcon} {tCategory(req.category, t)}</div>
                      </div>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.82rem', fontWeight: 700, padding: '6px 14px', borderRadius: 20, background: ss.bg, color: ss.color }}>{'\u25CF'} {t(`board.pipeline.${ss.key}`)}</div>
                      <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.82rem', color: '#9ca3af', textAlign: 'right' }}>{elapsed(req.created_at)}</div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* Announcements */}
        <div style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
          <div style={{ padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#f0ede6' }}>
            <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }}>{t('board.sections.announcements')}</div>
            <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: '#fef9e7', color: '#d97706' }}>{t('board.sections.important')}</div>
          </div>
          <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {ANNOUNCEMENTS.filter(a => a.title).map(ann => (
              <div key={ann.title} className="rb-ann" style={{ display: 'flex', gap: 16, padding: '18px 20px', borderRadius: 10, border: '1px solid rgba(0,0,0,0.06)', transition: 'box-shadow 0.2s' }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, background: ann.iconBg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.3rem', flexShrink: 0 }}>{ann.icon}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '0.95rem', marginBottom: 4 }}>{ann.title}</div>
                  {ann.text && <div style={{ fontSize: '0.85rem', color: '#6b7280', lineHeight: 1.5 }}>{ann.text}</div>}
                  <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.72rem', color: '#9ca3af', marginTop: 6 }}>{t('board.sections.published')} {ann.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Satisfaction + Working Hours */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {/* Satisfaction */}
          <div style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
            <div style={{ padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', background: '#f0ede6' }}>
              <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }}>{t('board.sections.residentRating')}</div>
            </div>
            <div style={{ padding: '20px 28px', textAlign: 'center' }}>
              <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 800, fontSize: '3.5rem', color: '#1a6b52', letterSpacing: '-0.04em', lineHeight: 1 }}>{satisfactionVal}</div>
              <div style={{ fontSize: '1.5rem', margin: '8px 0', letterSpacing: 4 }}>{'\u2605'.repeat(starFill)}{'\u2606'.repeat(5 - starFill)}</div>
              <div style={{ fontSize: '0.85rem', color: '#6b7280', fontWeight: 600 }}>{t('board.sections.efficiencyPeriod')}</div>
              <div style={{ width: '80%', margin: '16px auto 0', height: 8, background: '#f0ede6', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ height: '100%', borderRadius: 4, background: 'linear-gradient(90deg,#1a6b52,#059669)', width: `${satisfactionPct}%` }} />
              </div>
            </div>
          </div>

          {/* Working Hours */}
          <div style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
            <div style={{ padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', background: '#f0ede6' }}>
              <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }}>{t('board.sections.workingHours')}</div>
            </div>
            <div style={{ padding: '20px 28px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 8, textAlign: 'center' }}>
                {WORK_HOURS.map((d, i) => (
                  <div key={d.day}>
                    <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '0.78rem', color: i === todayDow ? '#1a6b52' : '#6b7280', marginBottom: 6 }}>{d.day}</div>
                    <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 600, padding: '8px 4px', borderRadius: 8, background: i === todayDow ? '#e8f5ef' : '#f0ede6', color: i === todayDow ? '#1a6b52' : '#1a1a1a', border: `2px solid ${i === todayDow ? '#1a6b52' : 'transparent'}` }}>{d.hours}</div>
                  </div>
                ))}
              </div>
              <div style={{ textAlign: 'center', marginTop: 16, padding: 12, background: '#fef2f2', borderRadius: 10, fontSize: '0.85rem', fontWeight: 600, color: '#dc2626' }}>
                {'\u{1F4DE}'} {t('board.sections.emergencyService')}
              </div>
              <div style={{ textAlign: 'center', marginTop: 10, fontSize: '0.82rem', color: '#6b7280' }}>
                {'\u{1F4F1}'} {t('board.ticker.telegramBot')}
              </div>
            </div>
          </div>
        </div>
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
