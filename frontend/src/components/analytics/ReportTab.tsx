import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import EmptyState from '../shared/EmptyState'
import LoadingSpinner from '../shared/LoadingSpinner'
import { SortIndicator } from '../shared/SortIndicator'
import { usePersonName } from '../../hooks/usePersonName'
import { useTableSort } from '../../hooks/useTableSort'
import { useReportRequests } from '../../hooks/useAnalytics'
import { tCategory, tStatus } from '../../i18n/apiMaps'
import { formatDateTime } from '../../utils/timezone'
import type { SortableColumn } from '../../utils/tableSort'
import type { DateRange } from '../../utils/analyticsPeriod'
import type { ReportRequestRow, ReportScope } from '../../types/api'
import { Panel, RequestLink, TableShell } from './shared'
import { TD, TH } from './analyticsFormat'
import ReportExportPanel from './ReportExportPanel'

/** Строк за раз: период до 5 лет — до 10 000 заявок, весь список в DOM не кладём. */
const PAGE = 100

type Row = ReportRequestRow & { id: number }

const COLUMNS: readonly (SortableColumn<Row> & { labelKey: string })[] = [
  { id: 'number', kind: 'text', value: r => r.request_number, labelKey: 'analytics.report.number' },
  { id: 'created', kind: 'date', value: r => r.created_at, labelKey: 'analytics.report.created' },
  { id: 'status', kind: 'text', value: r => r.status, labelKey: 'analytics.report.status' },
  { id: 'category', kind: 'text', value: r => r.category, labelKey: 'analytics.report.category' },
  { id: 'address', kind: 'text', value: r => r.address, labelKey: 'analytics.report.address' },
  { id: 'executor', kind: 'text', value: r => r.executor_name, labelKey: 'analytics.report.executor' },
  { id: 'completed', kind: 'date', value: r => r.completed_at, labelKey: 'analytics.report.completed' },
  { id: 'onTime', kind: 'number', value: r => (r.on_time === null ? null : Number(r.on_time)), labelKey: 'analytics.report.onTime' },
]

const SCOPES: readonly ReportScope[] = ['all', 'done']

export default function ReportTab({ range }: { range: DateRange }) {
  const { t } = useTranslation()
  const { name: personName } = usePersonName()
  const [scope, setScope] = useState<ReportScope>('all')
  const [shown, setShown] = useState(PAGE)
  const { data, isLoading, isError } = useReportRequests(range, scope)
  const sort = useTableSort(COLUMNS, 'analytics.report.sort')

  const { sortRows } = sort
  const rows = useMemo(() => sortRows((data?.rows ?? []).map((r, i) => ({ ...r, id: i + 1 }))), [data, sortRows])

  const switchScope = (next: ReportScope) => {
    setScope(next)
    setShown(PAGE)
  }

  const actions = (
    <div className="flex items-center gap-1" role="group" aria-label={t('analytics.report.scopeLabel')}>
      {SCOPES.map(key => (
        <Button
          key={key}
          size="sm"
          variant={scope === key ? 'default' : 'outline'}
          aria-pressed={scope === key}
          onClick={() => switchScope(key)}
        >
          {t(`analytics.report.scope.${key}`)}
        </Button>
      ))}
    </div>
  )

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('analytics.report.title')} actions={actions}>
        {isLoading ? (
          <LoadingSpinner />
        ) : isError ? (
          <span className="text-red text-[13px]">{t('analytics.loadError')}</span>
        ) : rows.length === 0 ? (
          <EmptyState icon={'\u{1F4CB}'} title={t('analytics.noData')} subtitle={t('analytics.noDataPeriod')} />
        ) : (
          <>
            <p className="text-[12px] text-text-muted mb-3">
              {t('analytics.report.total', { count: rows.length })}
              {data?.truncated && ` · ${t('analytics.report.truncated')}`}
            </p>
            <TableShell>
              <thead>
                <tr>
                  {COLUMNS.map(c => (
                    <th key={c.id} className={TH} aria-sort={sort.ariaSort(c.id)}>
                      <SortIndicator direction={sort.direction(c.id)} ariaSort={sort.ariaSort(c.id)} onToggle={() => sort.toggle(c.id)}>
                        {t(c.labelKey)}
                      </SortIndicator>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, shown).map(r => (
                  <tr key={r.request_number}>
                    <td className={`${TD} whitespace-nowrap`}><RequestLink number={r.request_number} /></td>
                    <td className={`${TD} whitespace-nowrap font-[family-name:var(--font-mono)]`}>
                      {r.created_at ? formatDateTime(r.created_at) : '—'}
                    </td>
                    <td className={`${TD} whitespace-nowrap`}>{tStatus(r.status, t)}</td>
                    <td className={TD}>{tCategory(r.category, t)}</td>
                    <td className={`${TD} max-w-[280px]`}>{r.address ?? '—'}</td>
                    <td className={TD}>{r.executor_name ? personName(r.executor_name, '—') : '—'}</td>
                    <td className={`${TD} whitespace-nowrap font-[family-name:var(--font-mono)]`}>
                      {r.completed_at ? formatDateTime(r.completed_at) : '—'}
                    </td>
                    <td className={TD}>
                      {r.on_time === null ? '—' : r.on_time
                        ? <span className="text-accent">{t('analytics.report.yes')}</span>
                        : <span className="text-red font-semibold">{t('analytics.report.no')}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
            {rows.length > shown && (
              <div className="mt-3">
                <Button size="sm" variant="outline" onClick={() => setShown(n => n + PAGE)}>
                  {t('analytics.report.more', { shown, total: rows.length })}
                </Button>
              </div>
            )}
          </>
        )}
      </Panel>
      <ReportExportPanel range={range} />
    </div>
  )
}
