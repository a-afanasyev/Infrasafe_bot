import { useTranslation } from 'react-i18next'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import EmptyState from '../shared/EmptyState'
import { tCategory } from '../../i18n/apiMaps'
import { fmtMoney } from '../../utils/materialsFormat'
import { formatBucket } from '../../utils/analyticsPeriod'
import type { ChannelStatsOut, CostStatsOut } from '../../types/api'
import { KpiCard, Panel, TableShell } from './shared'
import { MONTH_KEYS, PIE_PALETTE, TD, TH } from './analyticsFormat'

const KNOWN_SOURCES = ['bot', 'twa', 'group', 'call_center', 'web', 'api', 'infrasafe', 'inspector', 'dispatcher', 'unknown']

interface Props {
  channels: ChannelStatsOut | undefined
  costs: CostStatsOut | undefined
}

export default function ChannelsTab({ channels, costs }: Props) {
  const { t } = useTranslation()
  const months = MONTH_KEYS.map(k => t(`analytics.monthShort.${k}`))
  const sourceLabel = (s: string) => (KNOWN_SOURCES.includes(s) ? t(`analytics.source.${s}`) : s)

  const totals = channels ? Object.entries(channels.totals).sort((a, b) => b[1] - a[1]) : []
  const sources = totals.map(([s]) => s)
  const series = (channels?.series ?? []).map(p => ({
    bucket: p.bucket,
    ...Object.fromEntries(sources.map(s => [sourceLabel(s), p.counts[s] ?? 0])),
  }))

  return (
    <div className="flex flex-col gap-4">
      {channels && (
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_2fr] gap-4">
          <Panel title={t('analytics.channels.title')}>
            {totals.length === 0 ? (
              <EmptyState icon={'\u{1F4E8}'} title={t('analytics.noDataPeriod')} />
            ) : (
              <TableShell>
                <tbody>
                  {totals.map(([source, count], idx) => (
                    <tr key={source}>
                      <td className={TD}>
                        <span className="inline-block w-2.5 h-2.5 rounded-[2px] mr-2 align-middle" style={{ background: PIE_PALETTE[idx % PIE_PALETTE.length] }} />
                        {sourceLabel(source)}
                      </td>
                      <td className={`${TD} font-[family-name:var(--font-mono)] text-right`}>{count}</td>
                    </tr>
                  ))}
                </tbody>
              </TableShell>
            )}
          </Panel>
          <Panel title={t(`analytics.channels.series.${channels.granularity}`)}>
            {totals.length === 0 ? (
              <EmptyState icon={'\u{1F4CA}'} title={t('analytics.noDataPeriod')} />
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={series} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="bucket"
                    tickFormatter={(v: string) => formatBucket(v, channels.granularity, months)}
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={12}
                  />
                  <YAxis allowDecimals={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    labelFormatter={(v) => formatBucket(String(v), channels.granularity, months)}
                    contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', fontSize: 13 }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', color: 'var(--text-secondary)', paddingTop: 12 }} />
                  {sources.map((s, idx) => (
                    <Bar key={s} dataKey={sourceLabel(s)} stackId="src" fill={PIE_PALETTE[idx % PIE_PALETTE.length]} maxBarSize={28} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            )}
          </Panel>
        </div>
      )}

      {costs && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <KpiCard label={t('analytics.costs.total')} value={fmtMoney(costs.total)} hint={t('analytics.costs.hint')} />
            <KpiCard label={t('analytics.costs.withMaterials')} value={costs.requests_with_materials} />
            <KpiCard
              label={t('analytics.costs.avgPerRequest')}
              value={costs.requests_with_materials ? fmtMoney(costs.total / costs.requests_with_materials) : '—'}
            />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Panel title={t('analytics.costs.byCategory')}>
              {Object.keys(costs.by_category).length === 0 ? (
                <EmptyState icon={'\u{1F9F0}'} title={t('analytics.costs.none')} />
              ) : (
                <TableShell>
                  <thead>
                    <tr>
                      <th className={TH}>{t('analytics.quality.category')}</th>
                      <th className={`${TH} text-right`}>{t('analytics.costs.amount')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(costs.by_category).map(([category, amount]) => (
                      <tr key={category}>
                        <td className={TD}>{tCategory(category, t)}</td>
                        <td className={`${TD} font-[family-name:var(--font-mono)] text-right`}>{fmtMoney(amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              )}
            </Panel>
            <Panel title={t('analytics.costs.byBuilding')}>
              {costs.by_building.length === 0 ? (
                <EmptyState icon={'\u{1F3E0}'} title={t('analytics.costs.none')} />
              ) : (
                <TableShell>
                  <thead>
                    <tr>
                      <th className={TH}>{t('analytics.addresses.address')}</th>
                      <th className={`${TH} text-right`}>{t('analytics.costs.amount')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costs.by_building.map(b => (
                      <tr key={b.id}>
                        <td className={TD}>{b.name}</td>
                        <td className={`${TD} font-[family-name:var(--font-mono)] text-right`}>{fmtMoney(b.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              )}
            </Panel>
          </div>
        </>
      )}
    </div>
  )
}
