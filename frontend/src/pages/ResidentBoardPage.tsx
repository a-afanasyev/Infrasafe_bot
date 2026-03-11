import { useEffect, useState } from 'react'
import { useKanban } from '../hooks/useKanban'
import { useShiftStats, useRequestStats } from '../hooks/useAnalytics'

// ── helpers ──────────────────────────────────────────────────────────────────

function formatClock(d: Date) {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
function formatDateRu(d: Date) {
  const days = ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
  const months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
  return `${days[d.getDay()]}, ${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`
}
function formatUpdateTime(d: Date) {
  return `${formatClock(d)}:${String(d.getSeconds()).padStart(2, '0')}`
}
function elapsed(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 3600) return `${Math.round(diff / 60)} мин`
  if (diff < 86400) return `${Math.round(diff / 3600)} ч`
  return `${Math.round(diff / 86400)} д`
}

const CATEGORY_ICONS: Record<string, string> = {
  Сантехника: '🔧', Электрика: '⚡', Лифт: '🛗',
  Вентиляция: '💨', Уборка: '🧹', Отопление: '🔥',
  Безопасность: '🔒', Благоустройство: '🌿', Ремонт: '🏗️',
}

const PIPELINE = [
  { status: 'Новая',     label: 'Новые',     color: '#2563eb', bg: '#eff3ff' },
  { status: 'В работе',  label: 'В работе',  color: '#7c3aed', bg: '#f3f0ff' },
  { status: 'Закуп',     label: 'Закуп',     color: '#d97706', bg: '#fef9e7' },
  { status: 'Уточнение', label: 'Уточнение', color: '#0891b2', bg: '#ecfeff' },
  { status: 'Выполнена', label: 'Выполнена', color: '#059669', bg: '#ecfdf5' },
  { status: 'Принято',   label: 'Принято ✓', color: '#16a34a', bg: '#f0fdf4' },
]

const STATUS_STYLE: Record<string, { color: string; bg: string; label: string }> = {
  'Новая':     { color: '#2563eb', bg: '#eff3ff', label: 'Новая' },
  'В работе':  { color: '#7c3aed', bg: '#f3f0ff', label: 'В работе' },
  'Закуп':     { color: '#d97706', bg: '#fef9e7', label: 'Закуп' },
  'Уточнение': { color: '#0891b2', bg: '#ecfeff', label: 'Уточнение' },
  'Выполнена': { color: '#059669', bg: '#ecfdf5', label: 'Выполнена' },
  'Исполнено': { color: '#059669', bg: '#ecfdf5', label: 'Исполнено' },
  'Принято':   { color: '#16a34a', bg: '#f0fdf4', label: 'Принято' },
}

const ANNOUNCEMENTS = [
  { icon: '⚠️', iconBg: '#fef2f2', title: 'Плановое отключение горячей воды', text: '13–14 марта с 10:00 до 14:00 — промывка отопительной системы. Просим подготовить запас воды.', time: '10 марта, 09:00' },
  { icon: '📢', iconBg: '#eff3ff', title: 'Собрание собственников', text: 'Ежеквартальное собрание — 20 марта в 19:00 в холле. Итоги зимнего сезона, план благоустройства.', time: '9 марта, 14:30' },
  { icon: '🌿', iconBg: '#ecfdf5', title: 'Весенняя уборка территории', text: 'С 15 марта начинается генеральная уборка дворовой территории и подготовка к озеленению.', time: '8 марта, 11:00' },
]

const WORK_HOURS = [
  { day: 'Пн', hours: '08-20' }, { day: 'Вт', hours: '08-20' }, { day: 'Ср', hours: '08-20' },
  { day: 'Чт', hours: '08-20' }, { day: 'Пт', hours: '08-20' }, { day: 'Сб', hours: '09-17' }, { day: 'Вс', hours: '10-16' },
]

const DOT: React.CSSProperties = { display: 'inline-block', width: 6, height: 6, background: 'rgba(255,255,255,0.4)', borderRadius: '50%', margin: '0 32px', verticalAlign: 'middle' }

// ── Component ─────────────────────────────────────────────────────────────────

export default function ResidentBoardPage() {
  const [now, setNow] = useState(new Date())
  const { columns } = useKanban()
  const { data: shiftStats } = useShiftStats('7d')
  const { data: reqStats } = useRequestStats('30d')

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const colMap = Object.fromEntries(columns.map(c => [c.status, c]))
  const totalActive = ['Новая', 'В работе', 'Закуп', 'Уточнение'].reduce((s, k) => s + (colMap[k]?.count ?? 0), 0)
  const totalDone   = ['Выполнена', 'Исполнено', 'Принято'].reduce((s, k) => s + (colMap[k]?.count ?? 0), 0)

  const activeRequests = ['Новая', 'В работе', 'Закуп', 'Уточнение', 'Выполнена']
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
          📋 Новые заявки принимаются через Telegram-бот
          <span style={DOT} />
          🔧 На территории работают {shiftStats?.active_executors ?? '…'} специалистов
          <span style={DOT} />
          ✅ Выполнено заявок за месяц: {totalDone}
          <span style={DOT} />
          ⚠️ Плановые работы: промывка отопительной системы — 13 марта, 10:00–14:00
          <span style={DOT} />
          📞 Диспетчерская: +998 71 123-45-67 (круглосуточно)
          <span style={DOT} />
          📱 Telegram-бот: @uk_management_bot
          <span style={DOT} />
        </span>
      </div>

      {/* Header */}
      <header style={{ background: '#fff', borderBottom: '1px solid rgba(0,0,0,0.06)', padding: '24px 48px', display: 'flex', alignItems: 'center', gap: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', position: 'sticky', top: 0, zIndex: 50 }}>
        <div style={{ width: 52, height: 52, background: '#1a6b52', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Sora',sans-serif", fontWeight: 800, fontSize: '1.3rem', color: '#fff', flexShrink: 0 }}>УК</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.4rem', color: '#1a1a1a', letterSpacing: '-0.02em' }}>Управляющая компания</div>
          <div style={{ fontSize: '0.85rem', color: '#9ca3af', marginTop: 2 }}>ЖК Olmazor Business City · Информационное табло для жителей</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', color: '#1a1a1a', letterSpacing: '-0.02em', lineHeight: 1 }}>{formatClock(now)}</div>
          <div style={{ fontSize: '0.85rem', color: '#6b7280', marginTop: 4 }}>{formatDateRu(now)}</div>
        </div>
      </header>

      {/* Main grid */}
      <div style={{ padding: '32px 48px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, maxWidth: 1600, margin: '0 auto' }}>

        {/* Stats Banner */}
        <div style={{ gridColumn: '1/-1', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16 }}>
          {([
            { icon: '📋', iconBg: '#eff3ff', valColor: '#2563eb', label: 'Активных заявок',
              render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#2563eb' }}>{totalActive}</span> },
            { icon: '✅', iconBg: '#ecfdf5', valColor: '#059669', label: 'Выполнено за месяц',
              render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#059669' }}>{totalDone}</span> },
            { icon: '⏱', iconBg: '#fef9e7', valColor: '#d97706', label: 'Среднее время решения',
              render: () => <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '2rem', letterSpacing: '-0.03em', lineHeight: 1, color: '#d97706' }}>{avgResH}<span style={{ fontSize: '1rem', color: '#9ca3af' }}>ч</span></span> },
            { icon: '👥', iconBg: '#f3f0ff', valColor: '#7c3aed', label: 'Специалистов на смене',
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

        {/* Active Requests — full width */}
        <div style={{ gridColumn: '1/-1', background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
          <div style={{ padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#f0ede6' }}>
            <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem', letterSpacing: '-0.01em' }}>Текущие заявки</div>
            <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: '#eff3ff', color: '#2563eb' }}>{totalActive} активных</div>
          </div>
          <div style={{ padding: '20px 28px' }}>
            {/* Pipeline */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 20 }}>
              {PIPELINE.map((step, i) => (
                <div key={step.status} style={{ display: 'contents' }}>
                  <div style={{ flex: 1, textAlign: 'center', padding: '14px 8px', borderRadius: 10, background: step.bg, color: step.color }}>
                    <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '1.4rem', fontWeight: 700, display: 'block', marginBottom: 4 }}>{colMap[step.status]?.count ?? 0}</span>
                    <span style={{ fontSize: '0.7rem', fontWeight: 700, opacity: 0.8 }}>{step.label}</span>
                  </div>
                  {i < PIPELINE.length - 1 && <span style={{ color: '#9ca3af', fontSize: '1.2rem', flexShrink: 0 }}>→</span>}
                </div>
              ))}
            </div>

            {/* Request rows */}
            {activeRequests.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: '0.9rem' }}>Нет активных заявок</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {activeRequests.map(req => {
                  const ss = STATUS_STYLE[req.status] ?? { color: '#6b7280', bg: '#f3f4f6', label: req.status }
                  const catIcon = CATEGORY_ICONS[req.category] ?? '📋'
                  const descText = req.description
                    ? (req.description.length > 55 ? req.description.slice(0, 55) + '…' : req.description)
                    : req.category
                  return (
                    <div key={req.request_number} className="rb-req-row" style={{ display: 'grid', gridTemplateColumns: '110px 1fr 150px 90px', gap: 16, alignItems: 'center', padding: '14px 18px', borderRadius: 10, border: '1px solid rgba(0,0,0,0.06)', transition: 'background 0.15s', cursor: 'default' }}>
                      <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700, fontSize: '0.88rem', color: '#1a6b52' }}>#{req.request_number}</div>
                      <div>
                        <div style={{ fontSize: '0.93rem', fontWeight: 500, color: '#1a1a1a' }}>{descText}</div>
                        <div style={{ fontSize: '0.78rem', color: '#9ca3af', marginTop: 2 }}>{catIcon} {req.category}</div>
                      </div>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.82rem', fontWeight: 700, padding: '6px 14px', borderRadius: 20, background: ss.bg, color: ss.color }}>● {ss.label}</div>
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
            <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }}>Объявления</div>
            <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.75rem', fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: '#fef9e7', color: '#d97706' }}>Важное</div>
          </div>
          <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {ANNOUNCEMENTS.map(ann => (
              <div key={ann.title} className="rb-ann" style={{ display: 'flex', gap: 16, padding: '18px 20px', borderRadius: 10, border: '1px solid rgba(0,0,0,0.06)', transition: 'box-shadow 0.2s' }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, background: ann.iconBg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.3rem', flexShrink: 0 }}>{ann.icon}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '0.95rem', marginBottom: 4 }}>{ann.title}</div>
                  <div style={{ fontSize: '0.85rem', color: '#6b7280', lineHeight: 1.5 }}>{ann.text}</div>
                  <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '0.72rem', color: '#9ca3af', marginTop: 6 }}>Опубликовано: {ann.time}</div>
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
              <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }}>Оценка жителей</div>
            </div>
            <div style={{ padding: '20px 28px', textAlign: 'center' }}>
              <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontWeight: 800, fontSize: '3.5rem', color: '#1a6b52', letterSpacing: '-0.04em', lineHeight: 1 }}>{satisfactionVal}</div>
              <div style={{ fontSize: '1.5rem', margin: '8px 0', letterSpacing: 4 }}>{'★'.repeat(starFill)}{'☆'.repeat(5 - starFill)}</div>
              <div style={{ fontSize: '0.85rem', color: '#6b7280', fontWeight: 600 }}>Эффективность работы за период</div>
              <div style={{ width: '80%', margin: '16px auto 0', height: 8, background: '#f0ede6', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ height: '100%', borderRadius: 4, background: 'linear-gradient(90deg,#1a6b52,#059669)', width: `${satisfactionPct}%` }} />
              </div>
            </div>
          </div>

          {/* Working Hours */}
          <div style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
            <div style={{ padding: '20px 28px', borderBottom: '1px solid rgba(0,0,0,0.06)', background: '#f0ede6' }}>
              <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 700, fontSize: '1.1rem' }}>Часы работы</div>
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
                📞 Аварийная служба: круглосуточно
              </div>
              <div style={{ textAlign: 'center', marginTop: 10, fontSize: '0.82rem', color: '#6b7280' }}>
                📱 Telegram-бот: <strong>@uk_management_bot</strong>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer style={{ padding: '20px 48px', textAlign: 'center', color: '#9ca3af', fontSize: '0.82rem', borderTop: '1px solid rgba(0,0,0,0.06)', background: '#fff' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#059669', display: 'inline-block', animation: 'rb-pulse 2s ease-in-out infinite' }} />
          Обновление в реальном времени · Данные актуальны на {formatUpdateTime(now)}
        </span>
      </footer>
    </div>
  )
}
