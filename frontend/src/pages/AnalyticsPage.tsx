import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
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
import { tCategory, tStatus } from '../i18n/apiMaps'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import EmptyState from '../components/shared/EmptyState'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

// ── Constants ────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  'Новая': 'var(--blue)',
  'Уточнение': 'var(--amber)',
  'В работе': 'var(--accent)',
  'Закуп': 'var(--cyan)',
  'Выполнена': 'var(--emerald)',
  'Исполнено': 'var(--emerald)',
  'Принято': 'var(--emerald)',
  'Отменена': 'var(--text-muted)',
  rejected: 'var(--red)',
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

// ── Sub-components ───────────────────────────────────────────────────────────

interface KpiCardProps {
  label: string
  value: string | number
  valueColor: string
  topGradient: string
  change?: string
  changeColor?: string
}

function KpiCard({ label, value, valueColor, topGradient, change, changeColor }: KpiCardProps) {
  return (
    <div className="rounded-default bg-bg-card border border-border-default p-5 px-6 relative overflow-hidden cursor-default transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_8px_24px_rgba(0,0,0,0.3)] hover:border-border-active">
      {/* Top gradient strip */}
      <div
        className="absolute top-0 left-0 right-0 h-[3px]"
        style={{ background: topGradient }}
      />

      <div
        className="font-[family-name:var(--font-mono)] text-[1.75rem] font-bold leading-none mt-1"
        style={{ color: valueColor }}
      >
        {value}
      </div>

      <div className="text-sm text-text-secondary mt-1.5">
        {label}
      </div>

      {change !== undefined && (
        <div
          className="mt-2 text-xs font-semibold"
          style={{ color: changeColor ?? 'var(--text-muted)' }}
        >
          {change}
        </div>
      )}
    </div>
  )
}

// ── Custom recharts Tooltip ──────────────────────────────────────────────────

function BarTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; fill: string }>
  label?: string
}) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="bg-bg-surface border border-border-default rounded-sm p-2.5 px-3.5 text-[13px] font-[family-name:var(--font-body)]">
      <div className="text-text-secondary mb-1.5 font-semibold">
        {label}
      </div>
      {payload.map(p => (
        <div key={p.name} className="flex items-center gap-2 mb-0.5">
          <span
            className="inline-block w-2.5 h-2.5 rounded-[2px] shrink-0"
            style={{ background: p.fill }}
          />
          <span className="text-text-secondary">{p.name}:</span>
          <span className="text-text-primary font-[family-name:var(--font-mono)] font-semibold">
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
    <div className="bg-bg-surface border border-border-default rounded-sm p-2 px-3 text-[13px]">
      <span className="text-text-secondary">{item.name}: </span>
      <span className="text-text-primary font-[family-name:var(--font-mono)] font-semibold">
        {item.value}
      </span>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const { t } = useTranslation()
  usePageTitle(t('nav.analytics'))
  const [period, setPeriod] = useState<AnalyticsPeriod>('7d')
  const [clockStr, setClockStr] = useState('')

  const DAY_ABBR_KEYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const

  const periodOptions: { label: string; value: AnalyticsPeriod }[] = [
    { label: t('analytics.period7d'), value: '7d' },
    { label: t('analytics.period30d'), value: '30d' },
    { label: t('analytics.period90d'), value: '90d' },
  ]

  const createdLabel = t('analytics.created')
  const closedLabel = t('analytics.closed')

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
    [createdLabel]: d.created,
    [closedLabel]: d.closed,
  }))

  const byCategoryData = Object.entries(requestStats?.by_category ?? {}).map(
    ([name, value]) => ({ name: tCategory(name, t), value }),
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

  const rankLabel = (i: number) => ['\u{1F947}', '\u{1F948}', '\u{1F949}'][i] ?? `${i + 1}`

  return (
    <div className="p-5 px-6 flex flex-col gap-4">

      {/* ── Period selector bar ── */}
      <div className="flex items-center justify-between flex-wrap gap-2.5">
        <div className="flex gap-2">
          {periodOptions.map(opt => (
            <Button
              key={opt.value}
              variant={period === opt.value ? 'default' : 'outline'}
              size="sm"
              onClick={() => setPeriod(opt.value)}
              className="rounded-full"
            >
              {opt.label}
            </Button>
          ))}
        </div>

        <div className="text-xs text-text-muted font-[family-name:var(--font-mono)]">
          {t('analytics.updated')} {clockStr}
        </div>
      </div>

      {/* ── Inline error banner ── */}
      {hasError && (
        <div className="p-3 px-4 rounded-sm bg-red/10 border border-red/30 text-red text-[13px]">
          {t('analytics.loadError')}
        </div>
      )}

      {/* ── KPI grid ── */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          label={t('analytics.totalRequests')}
          value={requestStats?.total_requests ?? '—'}
          valueColor="var(--accent)"
          topGradient="linear-gradient(90deg, #00d4aa, #3b82f6)"
          change="—"
          changeColor="var(--text-muted)"
        />
        <KpiCard
          label={t('analytics.avgResolution')}
          value={requestStats?.avg_resolution_hours?.toFixed(1) ?? '—'}
          valueColor="var(--amber)"
          topGradient="linear-gradient(90deg, #f59e0b, #ef4444)"
          change="—"
          changeColor="var(--text-muted)"
        />
        <KpiCard
          label={t('analytics.satisfaction')}
          value={requestStats?.avg_satisfaction?.toFixed(1) ?? '—'}
          valueColor="var(--violet)"
          topGradient="linear-gradient(90deg, #8b5cf6, #3b82f6)"
          change="—"
          changeColor="var(--text-muted)"
        />
        <KpiCard
          label={t('analytics.onShiftNow')}
          value={shiftStats?.active_executors ?? '—'}
          valueColor="var(--emerald)"
          topGradient="linear-gradient(90deg, #10b981, #14b8a6)"
          change="—"
          changeColor="var(--text-muted)"
        />
      </div>

      {/* ── Charts row ── */}
      <div className="grid grid-cols-[2fr_1fr] gap-4">
        {/* Bar chart */}
        <div className="bg-bg-card border border-border-default rounded-default p-5 overflow-hidden">
          <div className="font-[family-name:var(--font-display)] font-semibold text-sm text-text-primary mb-4">{t('analytics.requestsByDay')}</div>
          {byDayData.length === 0 ? (
            <EmptyState icon={'\u{1F4CA}'} title={t('analytics.noData')} subtitle={t('analytics.noDataPeriod')} />
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
                  tickFormatter={(v: string) => t(`days.short.${DAY_ABBR_KEYS[toZonedTime(new Date(v), 'Asia/Tashkent').getDay()]}`)}
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
                <Bar dataKey={createdLabel} fill="var(--accent)" radius={[3, 3, 0, 0]} maxBarSize={28} />
                <Bar dataKey={closedLabel} fill="var(--blue)" radius={[3, 3, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Pie chart */}
        <div className="bg-bg-card border border-border-default rounded-default p-5 overflow-hidden relative">
          <div className="font-[family-name:var(--font-display)] font-semibold text-sm text-text-primary mb-4">{t('analytics.categoryBreakdown')}</div>
          {byCategoryData.length === 0 ? (
            <EmptyState icon={'\u{1F967}'} title={t('analytics.noData')} subtitle={t('analytics.noDataCategories')} />
          ) : (
            <>
              {/* Chart + center label */}
              <div className="relative">
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
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center pointer-events-none">
                  <div className="font-[family-name:var(--font-mono)] text-xl font-bold text-text-primary leading-none">
                    {byCategoryData.reduce((s, d) => s + d.value, 0)}
                  </div>
                  <div className="text-[11px] text-text-muted mt-0.5">
                    {t('analytics.requests')}
                  </div>
                </div>
              </div>

              {/* Legend */}
              <div className="flex flex-col gap-1.5 mt-2.5">
                {byCategoryData.map((d, idx) => (
                  <div key={d.name} className="flex items-center gap-2">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-[2px] shrink-0"
                      style={{ background: PIE_PALETTE[idx % PIE_PALETTE.length] }}
                    />
                    <span className="text-xs text-text-secondary flex-1 truncate">
                      {d.name}
                    </span>
                    <span className="text-xs font-[family-name:var(--font-mono)] text-text-primary">
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
      <div className="grid grid-cols-3 gap-4">
        {/* Col 1 — По статусам */}
        <div className="bg-bg-card border border-border-default rounded-default p-5 overflow-hidden">
          <div className="font-[family-name:var(--font-display)] font-semibold text-sm text-text-primary mb-4">{t('analytics.statusDistribution')}</div>
          {byStatusEntries.length === 0 ? (
            <EmptyState icon={'\u{1F4CB}'} title={t('analytics.noData')} />
          ) : (
            <div className="flex flex-col gap-2.5">
              {byStatusEntries.map(([status, count]) => {
                const pct = statusTotal > 0 ? Math.round((count / statusTotal) * 100) : 0
                const color = STATUS_COLORS[status] ?? 'var(--text-muted)'
                return (
                  <div key={status}>
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className="inline-block w-3 h-3 rounded-[3px] shrink-0"
                        style={{ background: color }}
                      />
                      <span className="flex-1 text-[13px] text-text-secondary truncate">
                        {tStatus(status, t)}
                      </span>
                      <span className="text-[13px] font-[family-name:var(--font-mono)] text-text-primary font-semibold">
                        {count}
                      </span>
                    </div>
                    {/* Progress bar */}
                    <div className="h-2 rounded bg-bg-surface overflow-hidden">
                      <div
                        className="h-full rounded transition-[width] duration-400 ease-out"
                        style={{ width: `${pct}%`, background: color }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Col 2 — Топ исполнителей */}
        <div className="bg-bg-card border border-border-default rounded-default p-5 overflow-hidden">
          <div className="font-[family-name:var(--font-display)] font-semibold text-sm text-text-primary mb-4">{t('analytics.topExecutors')}</div>
          {topExecutors.length === 0 ? (
            <EmptyState icon={'\u{1F3C6}'} title={t('analytics.noData')} />
          ) : (
            <div className="flex flex-col gap-3">
              {topExecutors.map((ex, idx) => {
                const parts = (ex.name ?? '').trim().split(' ')
                const firstName = parts[0] ?? null
                const lastName = parts[1] ?? null
                const initials = getInitials(firstName, lastName)
                const gradient = AVATAR_GRADIENTS[idx % AVATAR_GRADIENTS.length]

                return (
                  <div key={ex.user_id} className="flex items-center gap-2.5">
                    {/* Rank */}
                    <div
                      className="w-[22px] text-center font-[family-name:var(--font-mono)] shrink-0"
                      style={{
                        fontSize: idx < 3 ? '16px' : '13px',
                        color: rankColor(idx),
                      }}
                    >
                      {rankLabel(idx)}
                    </div>

                    {/* Avatar */}
                    <div
                      className="w-9 h-9 rounded-full flex items-center justify-center text-[13px] font-bold text-white shrink-0"
                      style={{ background: gradient }}
                    >
                      {initials}
                    </div>

                    {/* Info */}
                    <div className="flex-1 overflow-hidden">
                      <div className="text-[13px] font-semibold text-text-primary truncate">
                        {ex.name ?? t('analytics.unknown')}
                      </div>
                      <div className="text-[11px] text-text-muted mt-0.5">
                        {ex.completed} {t('analytics.requests')} · {ex.avg_hours?.toFixed(1) ?? '?'}{t('analytics.h')}
                      </div>
                    </div>

                    {/* Score */}
                    <div className="text-[13px] font-[family-name:var(--font-mono)] text-accent font-bold shrink-0">
                      {ex.score}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Col 3 — Последние действия */}
        <div className="bg-bg-card border border-border-default rounded-default p-5 overflow-hidden">
          <div className="font-[family-name:var(--font-display)] font-semibold text-sm text-text-primary mb-4">{t('analytics.recentActions')}</div>
          {recentActions.length === 0 ? (
            <EmptyState icon={'\u{1F4DC}'} title={t('analytics.noActions')} />
          ) : (
            <div className="flex flex-col">
              {recentActions.map((item, idx) => (
                <div
                  key={`${item.event_type}-${item.request_number}-${idx}`}
                  className={cn(
                    'py-2.5 flex items-start gap-2.5',
                    idx < recentActions.length - 1 && 'border-b border-border-default'
                  )}
                >
                  {/* Event dot */}
                  <span
                    className="inline-block w-2 h-2 rounded-full mt-1 shrink-0"
                    style={{ background: EVENT_COLORS[item.event_type] ?? 'var(--text-muted)' }}
                  />

                  <div className="flex-1 overflow-hidden">
                    <div className="text-[13px] text-text-secondary leading-snug truncate">
                      {t(`analyticsEvent.${item.event_type}`, item.event_type)}{' '}
                      <span className="text-text-primary font-semibold">
                        #{item.request_number}
                      </span>
                      {item.executor_name && (
                        <span className="text-text-muted">
                          {' \u00B7 '}{item.executor_name}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] font-[family-name:var(--font-mono)] text-text-muted mt-0.5">
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
