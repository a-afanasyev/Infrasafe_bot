import { useState, useEffect } from 'react'
import { toZonedTime } from 'date-fns-tz'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { useShiftStats, useRequestStats, type AnalyticsPeriod } from '../hooks/useAnalytics'
import { usePageTitle } from '../hooks/usePageTitle'
import { AVATAR_GRADIENTS, getInitials } from '../utils/employeeUtils'
import { formatDateTime } from '../utils/timezone'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import EmptyState from '../components/shared/EmptyState'

// ─── Constants ────────────────────────────────────────────────────────────────

const PERIOD_OPTIONS: { label: string; value: AnalyticsPeriod }[] = [
  { label: '7 дней', value: '7d' },
  { label: '30 дней', value: '30d' },
  { label: '90 дней', value: '90d' },
]

const DAY_ABBR = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']

const STATUS_COLORS: Record<string, string> = {
  new: 'var(--blue)',
  pending: 'var(--amber)',
  in_progress: 'var(--accent)',
  assigned: 'var(--cyan)',
  completed: 'var(--emerald)',
  cancelled: 'var(--text-muted)',
  rejected: 'var(--red)',
}

const STATUS_LABELS: Record<string, string> = {
  new: 'Новые',
  pending: 'В ожидании',
  in_progress: 'В работе',
  assigned: 'Назначены',
  completed: 'Завершены',
  cancelled: 'Отменены',
  rejected: 'Отклонены',
}

const EVENT_LABELS: Record<string, string> = {
  created: 'Создана',
  assigned: 'Назначена',
  completed: 'Завершена',
  cancelled: 'Отменена',
}

const EVENT_COLORS: Record<string, string> = {
  created: 'var(--accent)',
  assigned: 'var(--blue)',
  completed: 'var(--emerald)',
  cancelled: 'var(--red)',
}

const PIE_PALETTE = [
  '#00d4aa',
  '#3b82f6',
  '#8b5cf6',
  '#f59e0b',
  '#10b981',
  '#ef4444',
  '#06b6d4',
  '#14b8a6',
]

// ─── Static styles ────────────────────────────────────────────────────────────

const cardStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '20px',
  overflow: 'hidden',
}

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: 'var(--font-display)',
  fontWeight: 600,
  fontSize: '14px',
  color: 'var(--text-primary)',
  marginBottom: '16px',
}

// ─── Sub-components ───────────────────────────────────────────────────────────

interface KpiCardProps {
  label: string
  value: string | number
  valueColor: string
  topGradient: string
  change?: string
  changeColor?: string
}

function KpiCard({ label, value, valueColor, topGradient, change, changeColor }: KpiCardProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        borderRadius: 'var(--radius)',
        background: 'var(--bg-card)',
        border: `1px solid ${hovered ? 'var(--border-active)' : 'var(--border)'}`,
        padding: '20px 24px',
        position: 'relative',
        overflow: 'hidden',
        cursor: 'default',
        transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
        boxShadow: hovered
          ? '0 8px 24px rgba(0,0,0,0.3)'
          : '0 1px 4px rgba(0,0,0,0.15)',
        transition: 'transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease',
      }}
    >
      {/* Top gradient strip */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: topGradient,
        }}
      />

      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '1.75rem',
          fontWeight: 700,
          color: valueColor,
          lineHeight: 1,
          marginTop: 4,
        }}
      >
        {value}
      </div>

      <div
        style={{
          fontSize: '0.875rem',
          color: 'var(--text-secondary)',
          marginTop: 6,
        }}
      >
        {label}
      </div>

      {change !== undefined && (
        <div
          style={{
            marginTop: 8,
            fontSize: '12px',
            fontWeight: 600,
            color: changeColor ?? 'var(--text-muted)',
          }}
        >
          {change}
        </div>
      )}
    </div>
  )
}

// ─── Custom recharts Tooltip ──────────────────────────────────────────────────

function BarTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; fill: string }>
  label?: string
}) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: '10px 14px',
        fontSize: '13px',
        fontFamily: 'var(--font-body)',
      }}
    >
      <div style={{ color: 'var(--text-secondary)', marginBottom: 6, fontWeight: 600 }}>
        {label}
      </div>
      {payload.map(p => (
        <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
          <span
            style={{
              display: 'inline-block',
              width: 10,
              height: 10,
              borderRadius: 2,
              background: p.fill,
              flexShrink: 0,
            }}
          />
          <span style={{ color: 'var(--text-secondary)' }}>{p.name}:</span>
          <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
            {p.value}
          </span>
        </div>
      ))}
    </div>
  )
}

function PieTooltip({ active, payload }: {
  active?: boolean
  payload?: Array<{ name: string; value: number }>
}) {
  if (!active || !payload || payload.length === 0) return null
  const item = payload[0]
  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: '8px 12px',
        fontSize: '13px',
      }}
    >
      <span style={{ color: 'var(--text-secondary)' }}>{item.name}: </span>
      <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
        {item.value}
      </span>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  usePageTitle('Аналитика')
  const [period, setPeriod] = useState<AnalyticsPeriod>('7d')
  const [clockStr, setClockStr] = useState('')

  // Clock — update every minute (Tashkent time)
  useEffect(() => {
    const update = () => {
      const now = toZonedTime(new Date(), 'Asia/Tashkent')
      const hh = String(now.getHours()).padStart(2, '0')
      const mm = String(now.getMinutes()).padStart(2, '0')
      setClockStr(`${hh}:${mm}`)
    }
    update()
    const id = setInterval(update, 60_000)
    return () => clearInterval(id)
  }, [])

  const {
    data: shiftStats,
    isLoading: shiftLoading,
    isError: shiftError,
  } = useShiftStats(period)

  const {
    data: requestStats,
    isLoading: requestLoading,
    isError: requestError,
  } = useRequestStats(period)

  const isLoading = shiftLoading || requestLoading
  const hasError = shiftError || requestError

  if (isLoading) return <LoadingSpinner />

  // ── derived data ────────────────────────────────────────────────────────────

  const byDayData = (requestStats?.by_day ?? []).map(d => ({
    date: d.date,
    Создано: d.created,
    Закрыто: d.closed,
  }))

  const byCategoryData = Object.entries(requestStats?.by_category ?? {}).map(
    ([name, value]) => ({ name, value }),
  )

  const byStatusEntries = Object.entries(requestStats?.by_status ?? {})
  const statusTotal = byStatusEntries.reduce((s, [, v]) => s + v, 0)

  const topExecutors = (requestStats?.top_executors ?? []).slice(0, 5)
  const recentActions = (requestStats?.recent_actions ?? []).slice(0, 10)

  const rankColor = (i: number) => {
    if (i === 0) return 'var(--amber)'
    if (i === 1) return 'var(--text-secondary)'
    if (i === 2) return '#cd7f32'
    return 'var(--text-muted)'
  }

  const rankLabel = (i: number) => ['🥇', '🥈', '🥉'][i] ?? `${i + 1}`

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {/* ── Period selector bar ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', gap: '8px' }}>
          {PERIOD_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setPeriod(opt.value)}
              style={{
                padding: '6px 16px',
                borderRadius: 20,
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                fontFamily: 'var(--font-body)',
                transition: 'background 0.15s, color 0.15s, border-color 0.15s',
                background: period === opt.value ? 'var(--accent)' : 'var(--bg-surface)',
                color: period === opt.value ? '#000' : 'var(--text-secondary)',
                border: period === opt.value
                  ? '1px solid transparent'
                  : '1px solid var(--border)',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div
          style={{
            fontSize: '12px',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          Обновлено: {clockStr}
        </div>
      </div>

      {/* ── Inline error banner ── */}
      {hasError && (
        <div
          style={{
            padding: '12px 16px',
            borderRadius: 'var(--radius-sm)',
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
            color: 'var(--red)',
            fontSize: '13px',
          }}
        >
          Не удалось загрузить данные аналитики. Проверьте соединение.
        </div>
      )}

      {/* ── KPI grid ── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '16px',
        }}
      >
        <KpiCard
          label="Всего заявок"
          value={requestStats?.total_requests ?? '—'}
          valueColor="var(--accent)"
          topGradient="linear-gradient(90deg, #00d4aa, #3b82f6)"
          change="—"
          changeColor="var(--text-muted)"
        />
        <KpiCard
          label="Среднее время (ч)"
          value={requestStats?.avg_resolution_hours?.toFixed(1) ?? '—'}
          valueColor="var(--amber)"
          topGradient="linear-gradient(90deg, #f59e0b, #ef4444)"
          change="—"
          changeColor="var(--text-muted)"
        />
        <KpiCard
          label="Удовлетворённость"
          value={requestStats?.avg_satisfaction?.toFixed(1) ?? '—'}
          valueColor="var(--violet)"
          topGradient="linear-gradient(90deg, #8b5cf6, #3b82f6)"
          change="—"
          changeColor="var(--text-muted)"
        />
        <KpiCard
          label="На смене сейчас"
          value={shiftStats?.active_executors ?? '—'}
          valueColor="var(--emerald)"
          topGradient="linear-gradient(90deg, #10b981, #14b8a6)"
          change="—"
          changeColor="var(--text-muted)"
        />
      </div>

      {/* ── Charts row ── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '2fr 1fr',
          gap: '16px',
        }}
      >
        {/* Bar chart — заявки по дням */}
        <div style={cardStyle}>
          <div style={sectionTitleStyle}>Заявки по дням</div>
          {byDayData.length === 0 ? (
            <EmptyState icon="📊" title="Нет данных" subtitle="Данные за выбранный период отсутствуют" />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart
                data={byDayData}
                margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
                barCategoryGap="30%"
              >
                <CartesianGrid
                  stroke="var(--border)"
                  strokeDasharray="3 3"
                  vertical={false}
                />
                <XAxis
                  dataKey="date"
                  tickFormatter={(v: string) => DAY_ABBR[toZonedTime(new Date(v), 'Asia/Tashkent').getDay()] ?? v}
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<BarTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                <Legend
                  wrapperStyle={{ fontSize: '12px', color: 'var(--text-secondary)', paddingTop: 12 }}
                />
                <Bar dataKey="Создано" fill="var(--accent)" radius={[3, 3, 0, 0]} maxBarSize={28} />
                <Bar dataKey="Закрыто" fill="var(--blue)" radius={[3, 3, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Pie chart — по категориям */}
        <div style={{ ...cardStyle, position: 'relative' }}>
          <div style={sectionTitleStyle}>По категориям</div>
          {byCategoryData.length === 0 ? (
            <EmptyState icon="🥧" title="Нет данных" subtitle="Категории за период отсутствуют" />
          ) : (
            <>
              {/* Chart + center label */}
              <div style={{ position: 'relative' }}>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie
                      data={byCategoryData}
                      cx="50%"
                      cy="50%"
                      innerRadius={55}
                      outerRadius={82}
                      dataKey="value"
                      strokeWidth={0}
                    >
                      {byCategoryData.map((entry, idx) => (
                        <Cell
                          key={entry.name}
                          fill={PIE_PALETTE[idx % PIE_PALETTE.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={<PieTooltip />} />
                  </PieChart>
                </ResponsiveContainer>

                {/* Center label */}
                <div
                  style={{
                    position: 'absolute',
                    top: '50%',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                    textAlign: 'center',
                    pointerEvents: 'none',
                  }}
                >
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '20px',
                      fontWeight: 700,
                      color: 'var(--text-primary)',
                      lineHeight: 1,
                    }}
                  >
                    {byCategoryData.reduce((s, d) => s + d.value, 0)}
                  </div>
                  <div
                    style={{
                      fontSize: '11px',
                      color: 'var(--text-muted)',
                      marginTop: 3,
                    }}
                  >
                    заявок
                  </div>
                </div>
              </div>

              {/* Legend */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  marginTop: '10px',
                }}
              >
                {byCategoryData.map((d, idx) => (
                  <div
                    key={d.name}
                    style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
                  >
                    <span
                      style={{
                        display: 'inline-block',
                        width: 10,
                        height: 10,
                        borderRadius: 2,
                        background: PIE_PALETTE[idx % PIE_PALETTE.length],
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        fontSize: '12px',
                        color: 'var(--text-secondary)',
                        flex: 1,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {d.name}
                    </span>
                    <span
                      style={{
                        fontSize: '12px',
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-primary)',
                      }}
                    >
                      {d.value}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── Bottom grid ── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr 1fr',
          gap: '16px',
        }}
      >
        {/* Col 1 — По статусам */}
        <div style={cardStyle}>
          <div style={sectionTitleStyle}>По статусам</div>
          {byStatusEntries.length === 0 ? (
            <EmptyState icon="📋" title="Нет данных" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {byStatusEntries.map(([status, count]) => {
                const pct = statusTotal > 0 ? Math.round((count / statusTotal) * 100) : 0
                const color = STATUS_COLORS[status] ?? 'var(--text-muted)'
                return (
                  <div key={status}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        marginBottom: '4px',
                      }}
                    >
                      {/* Colored dot */}
                      <span
                        style={{
                          display: 'inline-block',
                          width: 12,
                          height: 12,
                          borderRadius: 3,
                          background: color,
                          flexShrink: 0,
                        }}
                      />
                      <span
                        style={{
                          flex: 1,
                          fontSize: '13px',
                          color: 'var(--text-secondary)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {STATUS_LABELS[status] ?? status}
                      </span>
                      <span
                        style={{
                          fontSize: '13px',
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-primary)',
                          fontWeight: 600,
                        }}
                      >
                        {count}
                      </span>
                    </div>
                    {/* Progress bar */}
                    <div
                      style={{
                        height: 8,
                        borderRadius: 4,
                        background: 'var(--bg-surface)',
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          height: '100%',
                          width: `${pct}%`,
                          borderRadius: 4,
                          background: color,
                          transition: 'width 0.4s ease',
                        }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Col 2 — Топ исполнителей */}
        <div style={cardStyle}>
          <div style={sectionTitleStyle}>Топ исполнителей</div>
          {topExecutors.length === 0 ? (
            <EmptyState icon="🏆" title="Нет данных" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {topExecutors.map((ex, idx) => {
                // Split name into first/last for initials
                const parts = (ex.name ?? '').trim().split(' ')
                const firstName = parts[0] ?? null
                const lastName = parts[1] ?? null
                const initials = getInitials(firstName, lastName)
                const gradient = AVATAR_GRADIENTS[idx % AVATAR_GRADIENTS.length]

                return (
                  <div
                    key={ex.user_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                    }}
                  >
                    {/* Rank */}
                    <div
                      style={{
                        width: 22,
                        textAlign: 'center',
                        fontSize: idx < 3 ? '16px' : '13px',
                        fontFamily: 'var(--font-mono)',
                        color: rankColor(idx),
                        flexShrink: 0,
                      }}
                    >
                      {rankLabel(idx)}
                    </div>

                    {/* Avatar */}
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: '50%',
                        background: gradient,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '13px',
                        fontWeight: 700,
                        color: '#fff',
                        flexShrink: 0,
                      }}
                    >
                      {initials}
                    </div>

                    {/* Info */}
                    <div style={{ flex: 1, overflow: 'hidden' }}>
                      <div
                        style={{
                          fontSize: '13px',
                          fontWeight: 600,
                          color: 'var(--text-primary)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {ex.name ?? 'Неизвестно'}
                      </div>
                      <div
                        style={{
                          fontSize: '11px',
                          color: 'var(--text-muted)',
                          marginTop: 2,
                        }}
                      >
                        {ex.completed} заявки · {ex.avg_hours?.toFixed(1) ?? '?'}ч
                      </div>
                    </div>

                    {/* Score */}
                    <div
                      style={{
                        fontSize: '13px',
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--accent)',
                        fontWeight: 700,
                        flexShrink: 0,
                      }}
                    >
                      {ex.score}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Col 3 — Последние действия */}
        <div style={cardStyle}>
          <div style={sectionTitleStyle}>Последние действия</div>
          {recentActions.length === 0 ? (
            <EmptyState icon="📜" title="Нет действий" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {recentActions.map((item, idx) => (
                <div
                  key={`${item.event_type}-${item.request_number}-${idx}`}
                  style={{
                    padding: '9px 0',
                    borderBottom:
                      idx < recentActions.length - 1 ? '1px solid var(--border)' : 'none',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '10px',
                  }}
                >
                  {/* Event dot */}
                  <span
                    style={{
                      display: 'inline-block',
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: EVENT_COLORS[item.event_type] ?? 'var(--text-muted)',
                      marginTop: 4,
                      flexShrink: 0,
                    }}
                  />

                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div
                      style={{
                        fontSize: '13px',
                        color: 'var(--text-secondary)',
                        lineHeight: '1.35',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {EVENT_LABELS[item.event_type] ?? item.event_type}{' '}
                      <span
                        style={{ color: 'var(--text-primary)', fontWeight: 600 }}
                      >
                        #{item.request_number}
                      </span>
                      {item.executor_name && (
                        <span style={{ color: 'var(--text-muted)' }}>
                          {' · '}{item.executor_name}
                        </span>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: '11px',
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-muted)',
                        marginTop: 2,
                      }}
                    >
                      {formatDateTime(item.created_at)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
