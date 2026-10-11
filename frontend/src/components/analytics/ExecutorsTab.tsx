import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight, Download } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import EmptyState from '../shared/EmptyState'
import LoadingSpinner from '../shared/LoadingSpinner'
import { SortIndicator } from '../shared/SortIndicator'
import { usePersonName } from '../../hooks/usePersonName'
import { useTableSort } from '../../hooks/useTableSort'
import {
  exportCompletedCsv,
  exportExecutorsCsv,
  useExecutorAcceptedRequests,
} from '../../hooks/useAnalytics'
import { tCategory } from '../../i18n/apiMaps'
import type { SortableColumn } from '../../utils/tableSort'
import type { DateRange } from '../../utils/analyticsPeriod'
import type { ExecutorStatsRow } from '../../types/api'
import { Panel, RequestLink, TableShell } from './shared'
import { TD, TH, fmtHours, fmtSum } from './analyticsFormat'

/** `useTableSort` ждёт числовой `id`; строка «без исполнителя» получает 0. */
type Row = ExecutorStatsRow & { id: number }

const COLUMNS: readonly (SortableColumn<Row> & { labelKey: string })[] = [
  { id: 'name', kind: 'text', value: r => r.name, labelKey: 'analytics.exec.name' },
  { id: 'executed', kind: 'number', value: r => r.executed, labelKey: 'analytics.exec.executed', defaultDirection: 'desc' },
  { id: 'accepted', kind: 'number', value: r => r.accepted, labelKey: 'analytics.exec.accepted', defaultDirection: 'desc' },
  { id: 'returned', kind: 'number', value: r => r.returned, labelKey: 'analytics.exec.returned', defaultDirection: 'desc' },
  { id: 'overdue', kind: 'number', value: r => r.overdue, labelKey: 'analytics.exec.overdue', defaultDirection: 'desc' },
  { id: 'work', kind: 'number', value: r => r.avg_work_hours, labelKey: 'analytics.exec.workHours' },
  { id: 'toAccept', kind: 'number', value: r => r.avg_to_accept_hours, labelKey: 'analytics.exec.toAcceptHours' },
  { id: 'rating', kind: 'number', value: r => r.avg_rating, labelKey: 'analytics.exec.rating', defaultDirection: 'desc' },
  { id: 'inWork', kind: 'number', value: r => r.in_work_now, labelKey: 'analytics.exec.inWork', defaultDirection: 'desc' },
  { id: 'materials', kind: 'money', value: r => r.materials_cost, labelKey: 'analytics.exec.materials', defaultDirection: 'desc' },
]

const byAcceptedDesc = (a: Row, b: Row) => b.accepted - a.accepted || b.executed - a.executed

function ExecutorRequests({ executorId, range, colSpan }: { executorId: number; range: DateRange; colSpan: number }) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useExecutorAcceptedRequests(executorId, range)
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-3 bg-bg-surface border-t border-border-default">
        {isLoading ? (
          <LoadingSpinner />
        ) : isError ? (
          <span className="text-red text-[13px]">{t('analytics.loadError')}</span>
        ) : !data || data.length === 0 ? (
          <span className="text-text-muted text-[13px]">{t('analytics.exec.noAccepted')}</span>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {data.map(r => (
              <li key={r.request_number} className="flex flex-wrap gap-x-3 gap-y-0.5 text-[13px]">
                <RequestLink number={r.request_number} />
                <span className="text-text-secondary">{tCategory(r.category, t)}</span>
                <span className="text-text-muted truncate max-w-[360px]">{r.address}</span>
              </li>
            ))}
            {data.length >= 200 && (
              <li className="text-[11px] text-text-muted">{t('analytics.exec.listTruncated')}</li>
            )}
          </ul>
        )}
      </td>
    </tr>
  )
}

interface Props {
  rows: ExecutorStatsRow[]
  range: DateRange
}

export default function ExecutorsTab({ rows, range }: Props) {
  const { t } = useTranslation()
  const { name: personName } = usePersonName()
  const [expanded, setExpanded] = useState<number | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const sort = useTableSort<Row>(COLUMNS, 'analytics.executors.sort', byAcceptedDesc)
  const sorted = sort.sortRows(rows.map(r => ({ ...r, id: r.user_id ?? 0 })))

  const download = async (key: string, run: () => Promise<void>) => {
    setBusy(key)
    try {
      await run()
    } catch {
      toast.error(t('analytics.exportFailed'))
    } finally {
      setBusy(null)
    }
  }

  const actions = (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => download('summary', () => exportExecutorsCsv(range))}>
        <Download size={14} /> {t('analytics.exec.exportSummary')}
      </Button>
      <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => download('all', () => exportCompletedCsv(range))}>
        <Download size={14} /> {t('analytics.exec.exportAll')}
      </Button>
    </div>
  )

  return (
    <Panel title={t('analytics.exec.title')} actions={actions}>
      <p className="text-[12px] text-text-muted mb-3">{t('analytics.exec.legend')}</p>
      {sorted.length === 0 ? (
        <EmptyState icon={'\u{1F477}'} title={t('analytics.noData')} subtitle={t('analytics.noDataPeriod')} />
      ) : (
        <TableShell>
          <thead>
            <tr>
              <th className={TH} />
              {COLUMNS.map(c => (
                <th key={c.id} className={TH} aria-sort={sort.ariaSort(c.id)}>
                  <SortIndicator direction={sort.direction(c.id)} ariaSort={sort.ariaSort(c.id)} onToggle={() => sort.toggle(c.id)}>
                    {t(c.labelKey)}
                  </SortIndicator>
                </th>
              ))}
              <th className={TH} />
            </tr>
          </thead>
          <tbody>
            {sorted.map(r => {
              const canExpand = r.user_id !== null && r.accepted > 0
              const open = canExpand && expanded === r.user_id
              return (
                <Fragment key={r.id}>
                  <tr className={canExpand ? 'cursor-pointer hover:bg-bg-surface' : undefined} onClick={() => canExpand && setExpanded(open ? null : r.user_id)}>
                    <td className={TD}>
                      {canExpand && (open ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
                    </td>
                    <td className={`${TD} font-semibold text-text-primary`}>
                      {r.user_id === null ? t('analytics.exec.noExecutor') : personName(r.name, t('analytics.unknown'))}
                    </td>
                    <td className={`${TD} font-[family-name:var(--font-mono)]`}>{r.executed}</td>
                    <td className={`${TD} font-[family-name:var(--font-mono)] font-semibold`}>{r.accepted}</td>
                    <td className={`${TD} font-[family-name:var(--font-mono)]`}>{r.returned}</td>
                    <td className={`${TD} font-[family-name:var(--font-mono)]`}>{r.overdue}</td>
                    <td className={`${TD} font-[family-name:var(--font-mono)]`}>{fmtHours(r.avg_work_hours)}</td>
                    <td className={`${TD} font-[family-name:var(--font-mono)]`}>{fmtHours(r.avg_to_accept_hours)}</td>
                    <td className={`${TD} font-[family-name:var(--font-mono)]`}>
                      {r.avg_rating?.toFixed(1) ?? '—'}
                      {r.ratings_count > 0 && <span className="text-text-muted"> ({r.ratings_count})</span>}
                    </td>
                    <td className={`${TD} font-[family-name:var(--font-mono)]`}>{r.in_work_now}</td>
                    <td className={`${TD} font-[family-name:var(--font-mono)] whitespace-nowrap`}>
                      {r.materials_cost > 0 ? fmtSum(r.materials_cost) : '—'}
                    </td>
                    <td className={TD} onClick={e => e.stopPropagation()}>
                      {r.user_id !== null && r.accepted > 0 && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          aria-label={t('analytics.exec.exportOne', { name: personName(r.name, t('analytics.unknown')) })}
                          disabled={busy !== null}
                          onClick={() => download(`one-${r.user_id}`, () => exportCompletedCsv(range, r.user_id!))}
                        >
                          <Download size={14} />
                        </Button>
                      )}
                    </td>
                  </tr>
                  {open && <ExecutorRequests executorId={r.user_id!} range={range} colSpan={COLUMNS.length + 2} />}
                </Fragment>
              )
            })}
          </tbody>
        </TableShell>
      )}
      <p className="text-[11px] text-text-muted mt-3">
        {t('analytics.exec.note')}
      </p>
    </Panel>
  )
}
