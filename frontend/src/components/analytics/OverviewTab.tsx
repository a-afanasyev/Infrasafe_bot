import { useTranslation } from 'react-i18next'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import EmptyState from '../shared/EmptyState'
import { tCategory, tStatus, type ApiStatus } from '../../i18n/apiMaps'
import { formatBucket, pctChange } from '../../utils/analyticsPeriod'
import type { RequestStatsOut, StatsKpi } from '../../types/api'
import { ChangeBadge, KpiCard, Panel } from './shared'
import { MONTH_KEYS, PIE_PALETTE, fmtHours } from './analyticsFormat'

// «Возвращена» — оранжевый: возврат не должен сливаться с выполненным.
const STATUS_COLORS: Partial<Record<ApiStatus, string>> = {
  'Новая': 'var(--blue)',
  'Уточнение': 'var(--amber)',
  'В работе': 'var(--accent)',
  'Закуп': 'var(--cyan)',
}

interface Props {
  stats: RequestStatsOut
  onShiftNow: number | null
}

type KpiKey = keyof StatsKpi

export default function OverviewTab({ stats, onShiftNow }: Props) {
  const { t } = useTranslation()
  const months = MONTH_KEYS.map(k => t(`analytics.monthShort.${k}`))
  const createdLabel = t('analytics.created')
  const acceptedLabel = t('analytics.accepted')
  const vsPrevious = t('analytics.vsPrevious')

  const change = (key: KpiKey, better: 'up' | 'down') => (
    <ChangeBadge pct={pctChange(stats.kpi[key], stats.previous[key])} better={better} title={vsPrevious} />
  )

  const series = stats.series.map(p => ({
    bucket: p.bucket,
    [createdLabel]: p.created,
    [acceptedLabel]: p.accepted,
  }))
  const hasSeries = stats.series.some(p => p.created > 0 || p.accepted > 0)

  const categories = Object.entries(stats.by_category)
    .map(([name, value]) => ({ name: tCategory(name, t), value }))
    .sort((a, b) => b.value - a.value)
  const categoryTotal = categories.reduce((s, d) => s + d.value, 0)

  const statuses = Object.entries(stats.open_by_status).sort((a, b) => b[1] - a[1])
  const statusTotal = statuses.reduce((s, [, v]) => s + v, 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <KpiCard label={t('analytics.kpi.created')} value={stats.kpi.created} change={change('created', 'up')} />
        <KpiCard label={t('analytics.kpi.accepted')} value={stats.kpi.accepted} change={change('accepted', 'up')} />
        <KpiCard
          label={t('analytics.kpi.workHours')}
          value={fmtHours(stats.kpi.avg_work_hours)}
          hint={t('analytics.kpi.workHoursHint')}
          change={change('avg_work_hours', 'down')}
        />
        <KpiCard
          label={t('analytics.kpi.toAcceptHours')}
          value={fmtHours(stats.kpi.avg_to_accept_hours)}
          hint={t('analytics.kpi.assignHours', { hours: fmtHours(stats.kpi.avg_assign_hours) })}
          change={change('avg_to_accept_hours', 'down')}
        />
        <KpiCard
          label={t('analytics.kpi.satisfaction')}
          value={stats.kpi.avg_satisfaction?.toFixed(1) ?? '—'}
          change={change('avg_satisfaction', 'up')}
        />
        <KpiCard
          label={t('analytics.kpi.returned')}
          value={stats.kpi.returned}
          hint={onShiftNow != null ? t('analytics.kpi.onShiftNow', { n: onShiftNow }) : undefined}
          change={change('returned', 'down')}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[2fr_1fr] gap-4">
        <Panel title={t(`analytics.seriesTitle.${stats.granularity}`)}>
          {!hasSeries ? (
            <EmptyState icon={'\u{1F4CA}'} title={t('analytics.noData')} subtitle={t('analytics.noDataPeriod')} />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={series} margin={{ top: 4, right: 8, left: -20, bottom: 0 }} barCategoryGap="25%">
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="bucket"
                  tickFormatter={(v: string) => formatBucket(v, stats.granularity, months)}
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={12}
                />
                <YAxis allowDecimals={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  labelFormatter={(v) => formatBucket(String(v), stats.granularity, months)}
                  contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', fontSize: 13 }}
                  cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                />
                <Legend wrapperStyle={{ fontSize: '12px', color: 'var(--text-secondary)', paddingTop: 12 }} />
                <Bar dataKey={createdLabel} fill="var(--accent)" radius={[3, 3, 0, 0]} maxBarSize={28} />
                <Bar dataKey={acceptedLabel} fill="var(--blue)" radius={[3, 3, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title={t('analytics.categoryBreakdown')}>
          {categories.length === 0 ? (
            <EmptyState icon={'\u{1F967}'} title={t('analytics.noData')} subtitle={t('analytics.noDataCategories')} />
          ) : (
            <>
              <div className="relative">
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie data={categories} cx="50%" cy="50%" innerRadius={55} outerRadius={82} dataKey="value" strokeWidth={0}>
                      {categories.map((entry, idx) => (
                        <Cell key={entry.name} fill={PIE_PALETTE[idx % PIE_PALETTE.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center pointer-events-none">
                  <div className="font-[family-name:var(--font-mono)] text-xl font-bold text-text-primary leading-none">
                    {categoryTotal}
                  </div>
                  <div className="text-[11px] text-text-muted mt-0.5">{t('analytics.requests')}</div>
                </div>
              </div>
              <div className="flex flex-col gap-1.5 mt-2.5">
                {categories.map((d, idx) => (
                  <div key={d.name} className="flex items-center gap-2">
                    <span className="inline-block w-2.5 h-2.5 rounded-[2px] shrink-0" style={{ background: PIE_PALETTE[idx % PIE_PALETTE.length] }} />
                    <span className="text-xs text-text-secondary flex-1 truncate">{d.name}</span>
                    <span className="text-xs font-[family-name:var(--font-mono)] text-text-primary">{d.value}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Panel>
      </div>

      <Panel title={t('analytics.openByStatus')}>
        {statuses.length === 0 ? (
          <EmptyState icon={'\u{1F4CB}'} title={t('analytics.noOpen')} />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2.5">
            {statuses.map(([status, count]) => {
              const pct = statusTotal > 0 ? Math.round((count / statusTotal) * 100) : 0
              const color = STATUS_COLORS[status as ApiStatus] ?? 'var(--text-muted)'
              return (
                <div key={status}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="inline-block w-3 h-3 rounded-[3px] shrink-0" style={{ background: color }} />
                    <span className="flex-1 text-[13px] text-text-secondary truncate">{tStatus(status, t)}</span>
                    <span className="text-[13px] font-[family-name:var(--font-mono)] text-text-primary font-semibold">{count}</span>
                  </div>
                  <div className="h-2 rounded bg-bg-surface overflow-hidden">
                    <div className="h-full rounded" style={{ width: `${pct}%`, background: color }} />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Panel>
    </div>
  )
}
