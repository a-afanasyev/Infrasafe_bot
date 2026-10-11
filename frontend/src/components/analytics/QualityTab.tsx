import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import EmptyState from '../shared/EmptyState'
import { useCan } from '../../hooks/useCan'
import { usePersonName } from '../../hooks/usePersonName'
import { useAutoManagerConfig, useUpdateAutoManagerConfig } from '../../hooks/useAutoManagerConfig'
import { tCategory, tUrgency } from '../../i18n/apiMaps'
import { formatDateTime } from '../../utils/timezone'
import type { QualityStatsOut } from '../../types/api'
import type { SlaHours } from '../../types/autoManagerConfig'
import { Panel, RequestLink, TableShell } from './shared'
import { TD, TH, fmtHours } from './analyticsFormat'

const URGENCIES = ['critical', 'high', 'medium', 'low'] as const
const SLA_MAX = 8784

function SlaEditor({ current }: { current: SlaHours }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const update = useUpdateAutoManagerConfig()
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(URGENCIES.map(u => [u, String(current[u])])))
  const parsed = Object.fromEntries(URGENCIES.map(u => [u, Number(draft[u])])) as unknown as SlaHours
  const valid = URGENCIES.every(u => Number.isInteger(parsed[u]) && parsed[u] >= 1 && parsed[u] <= SLA_MAX)
  const dirty = URGENCIES.some(u => parsed[u] !== current[u])

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={e => {
        e.preventDefault()
        if (!valid) return
        update.mutate({ sla_hours: parsed }, {
          onSuccess: () => queryClient.invalidateQueries({ queryKey: ['request-stats'] }),
        })
      }}
    >
      {URGENCIES.map(u => (
        <label key={u} className="flex flex-col gap-1 text-[12px] text-text-secondary">
          {tUrgency(u, t)}, {t('analytics.h')}
          <Input
            type="number"
            min={1}
            max={SLA_MAX}
            step={1}
            value={draft[u]}
            onChange={e => setDraft({ ...draft, [u]: e.target.value })}
            className="h-8 w-[90px]"
          />
        </label>
      ))}
      <Button type="submit" size="sm" disabled={!valid || !dirty || update.isPending}>
        {t('analytics.quality.saveSla')}
      </Button>
      {!valid && <span className="text-[12px] text-red">{t('analytics.quality.slaInvalid', { max: SLA_MAX })}</span>}
    </form>
  )
}

export default function QualityTab({ data }: { data: QualityStatsOut }) {
  const { t } = useTranslation()
  const { name: personName } = usePersonName()
  const canConfigure = useCan('auto_manager.configure')
  const config = useAutoManagerConfig()
  const ratingsTotal = Object.values(data.ratings).reduce((s, n) => s + n, 0)

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('analytics.quality.slaTitle')}>
        <p className="text-[12px] text-text-muted mb-3">{t('analytics.quality.slaLegend')}</p>
        <TableShell>
          <thead>
            <tr>
              <th className={TH}>{t('analytics.quality.urgency')}</th>
              <th className={TH}>{t('analytics.quality.norm')}</th>
              <th className={TH}>{t('analytics.quality.accepted')}</th>
              <th className={TH}>{t('analytics.quality.median')}</th>
              <th className={TH}>{t('analytics.quality.p90')}</th>
              <th className={TH}>{t('analytics.quality.overdue')}</th>
            </tr>
          </thead>
          <tbody>
            {data.by_urgency.map(u => {
              const share = u.measured > 0 ? Math.round((u.overdue / u.measured) * 100) : null
              return (
                <tr key={u.urgency}>
                  <td className={TD}>{tUrgency(u.urgency, t)}</td>
                  <td className={`${TD} font-[family-name:var(--font-mono)]`}>{u.sla_hours}</td>
                  <td className={`${TD} font-[family-name:var(--font-mono)]`}>{u.accepted}</td>
                  <td className={`${TD} font-[family-name:var(--font-mono)]`}>{fmtHours(u.median_hours)}</td>
                  <td className={`${TD} font-[family-name:var(--font-mono)]`}>{fmtHours(u.p90_hours)}</td>
                  <td className={`${TD} font-[family-name:var(--font-mono)]`} style={{ color: u.overdue ? 'var(--red)' : undefined }}>
                    {u.overdue}{share !== null && ` (${share}%)`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </TableShell>
        {canConfigure && config.data?.sla_hours && (
          <div className="mt-4 pt-4 border-t border-border-default">
            <div className="text-[12px] text-text-secondary mb-2">{t('analytics.quality.editSla')}</div>
            <SlaEditor key={JSON.stringify(config.data.sla_hours)} current={config.data.sla_hours} />
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title={t('analytics.quality.returnsTitle')}>
          {data.returns_by_category.length === 0 ? (
            <EmptyState icon={'\u{1F504}'} title={t('analytics.noData')} />
          ) : (
            <TableShell>
              <thead>
                <tr>
                  <th className={TH}>{t('analytics.quality.category')}</th>
                  <th className={TH}>{t('analytics.quality.accepted')}</th>
                  <th className={TH}>{t('analytics.quality.returned')}</th>
                </tr>
              </thead>
              <tbody>
                {data.returns_by_category.map(c => (
                  <tr key={c.category}>
                    <td className={TD}>{tCategory(c.category, t)}</td>
                    <td className={`${TD} font-[family-name:var(--font-mono)]`}>{c.accepted}</td>
                    <td className={`${TD} font-[family-name:var(--font-mono)]`}>
                      {c.returned} ({Math.round((c.returned / c.accepted) * 100)}%)
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          )}
        </Panel>

        <Panel title={t('analytics.quality.ratingsTitle')}>
          {ratingsTotal === 0 ? (
            <EmptyState icon={'\u{2B50}'} title={t('analytics.quality.noRatings')} />
          ) : (
            <div className="flex flex-col gap-2">
              {['5', '4', '3', '2', '1'].map(score => {
                const n = data.ratings[score] ?? 0
                const pct = Math.round((n / ratingsTotal) * 100)
                return (
                  <div key={score} className="flex items-center gap-2 text-[13px]">
                    <span className="w-8 font-[family-name:var(--font-mono)]">{score}★</span>
                    <div className="flex-1 h-2 rounded bg-bg-surface overflow-hidden">
                      <div className="h-full rounded bg-amber" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="w-14 text-right font-[family-name:var(--font-mono)]">{n}</span>
                  </div>
                )
              })}
            </div>
          )}
        </Panel>
      </div>

      <Panel title={t('analytics.quality.reviewsTitle')}>
        {data.recent_reviews.length === 0 ? (
          <EmptyState icon={'\u{1F4AC}'} title={t('analytics.quality.noReviews')} />
        ) : (
          <ul className="flex flex-col divide-y divide-border-default">
            {data.recent_reviews.map(r => (
              <li key={r.request_number} className="py-2.5 flex flex-col gap-0.5">
                <div className="flex flex-wrap items-center gap-x-3 text-[12px] text-text-muted">
                  <span className="text-amber font-semibold">{r.rating}★</span>
                  <RequestLink number={r.request_number} />
                  {r.executor_name && <span>{personName(r.executor_name)}</span>}
                  {r.completed_at && <span>{formatDateTime(r.completed_at)}</span>}
                </div>
                <div className="text-[13px] text-text-primary whitespace-pre-wrap break-words">{r.review}</div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
