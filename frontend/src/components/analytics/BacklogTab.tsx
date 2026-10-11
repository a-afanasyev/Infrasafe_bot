import { useTranslation } from 'react-i18next'
import EmptyState from '../shared/EmptyState'
import { usePersonName } from '../../hooks/usePersonName'
import { tCategory, tStatus } from '../../i18n/apiMaps'
import type { AddressStatsOut, BacklogOut } from '../../types/api'
import { KpiCard, Panel, RequestLink, TableShell } from './shared'
import { TD, TH } from './analyticsFormat'

const AGE_KEYS = ['lt1', 'd1_3', 'd3_7', 'd7_30', 'gt30'] as const

function TopList({ items, empty }: { items: { id: number; name: string; count: number }[]; empty: string }) {
  if (items.length === 0) return <EmptyState icon={'\u{1F3E0}'} title={empty} />
  const max = Math.max(...items.map(i => i.count))
  return (
    <div className="flex flex-col gap-2">
      {items.map(i => (
        <div key={i.id} className="text-[13px]">
          <div className="flex justify-between gap-2 mb-1">
            <span className="text-text-secondary truncate">{i.name}</span>
            <span className="font-[family-name:var(--font-mono)] text-text-primary">{i.count}</span>
          </div>
          <div className="h-1.5 rounded bg-bg-surface overflow-hidden">
            <div className="h-full rounded bg-accent" style={{ width: `${Math.round((i.count / max) * 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

interface Props {
  backlog: BacklogOut | undefined
  addresses: AddressStatsOut | undefined
}

export default function BacklogTab({ backlog, addresses }: Props) {
  const { t } = useTranslation()
  const { name: personName } = usePersonName()

  return (
    <div className="flex flex-col gap-4">
      {backlog && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
            <KpiCard label={t('analytics.backlog.total')} value={backlog.total} hint={t('analytics.backlog.now')} />
            {AGE_KEYS.map(k => (
              <KpiCard key={k} label={t(`analytics.backlog.age.${k}`)} value={backlog.by_age[k] ?? 0} />
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4">
            <Panel title={t('analytics.backlog.queues')}>
              {backlog.queues.length === 0 ? (
                <EmptyState icon={'\u{2705}'} title={t('analytics.noOpen')} />
              ) : (
                <TableShell>
                  <thead>
                    <tr>
                      <th className={TH}>{t('analytics.exec.name')}</th>
                      <th className={TH}>{t('analytics.backlog.open')}</th>
                      <th className={TH}>{t('analytics.backlog.oldestDays')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backlog.queues.map(q => (
                      <tr key={q.user_id ?? 'none'}>
                        <td className={TD}>
                          {q.user_id === null ? t('analytics.backlog.unassigned') : personName(q.name, t('analytics.unknown'))}
                        </td>
                        <td className={`${TD} font-[family-name:var(--font-mono)]`}>{q.open}</td>
                        <td className={`${TD} font-[family-name:var(--font-mono)]`}>{q.oldest_age_days.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              )}
            </Panel>

            <Panel title={t('analytics.backlog.oldest')}>
              {backlog.oldest.length === 0 ? (
                <EmptyState icon={'\u{2705}'} title={t('analytics.noOpen')} />
              ) : (
                <TableShell>
                  <thead>
                    <tr>
                      <th className={TH}>{t('analytics.backlog.request')}</th>
                      <th className={TH}>{t('analytics.backlog.status')}</th>
                      <th className={TH}>{t('analytics.quality.category')}</th>
                      <th className={TH}>{t('analytics.exec.name')}</th>
                      <th className={TH}>{t('analytics.backlog.ageDays')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backlog.oldest.map(r => (
                      <tr key={r.request_number}>
                        <td className={TD}><RequestLink number={r.request_number} /></td>
                        <td className={TD}>{tStatus(r.status, t)}</td>
                        <td className={TD}>{tCategory(r.category, t)}</td>
                        <td className={TD}>
                          {r.executor_id === null ? '—' : personName(r.executor_name, t('analytics.unknown'))}
                        </td>
                        <td className={`${TD} font-[family-name:var(--font-mono)]`}>{r.age_days.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              )}
            </Panel>
          </div>
        </>
      )}

      {addresses && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Panel title={t('analytics.addresses.buildings')}>
              <TopList items={addresses.buildings} empty={t('analytics.noDataPeriod')} />
            </Panel>
            <Panel title={t('analytics.addresses.yards')}>
              <TopList items={addresses.yards} empty={t('analytics.noDataPeriod')} />
            </Panel>
          </div>
          <Panel title={t('analytics.addresses.repeats')}>
            <p className="text-[12px] text-text-muted mb-3">{t('analytics.addresses.repeatsLegend')}</p>
            {addresses.repeats.length === 0 ? (
              <EmptyState icon={'\u{1F501}'} title={t('analytics.addresses.noRepeats')} />
            ) : (
              <TableShell>
                <thead>
                  <tr>
                    <th className={TH}>{t('analytics.backlog.request')}</th>
                    <th className={TH}>{t('analytics.addresses.previous')}</th>
                    <th className={TH}>{t('analytics.quality.category')}</th>
                    <th className={TH}>{t('analytics.addresses.address')}</th>
                    <th className={TH}>{t('analytics.addresses.daysAfter')}</th>
                  </tr>
                </thead>
                <tbody>
                  {addresses.repeats.map(r => (
                    <tr key={r.request_number}>
                      <td className={TD}><RequestLink number={r.request_number} /></td>
                      <td className={TD}><RequestLink number={r.previous_number} /></td>
                      <td className={TD}>{tCategory(r.category, t)}</td>
                      <td className={`${TD} text-text-secondary`}>{r.address ?? '—'}</td>
                      <td className={`${TD} font-[family-name:var(--font-mono)]`}>{r.days_after.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableShell>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}
