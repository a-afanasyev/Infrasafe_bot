import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { AccessRequestRow } from '../../types/access'
import { AccessStatusBadge } from './AccessBadges'
import { formatDateTime } from '../../utils/accessFormat'
import EmptyState from '../shared/EmptyState'
import { Button } from '@/components/ui/button'

/**
 * Таблица заявок жителей на постоянный автомобиль (экран менеджера).
 *
 * `actions` — рассмотрение заявки (подтвердить/отклонить); кнопки показываются
 * только у заявок в статусе pending. Передаётся лишь для manager/system_admin.
 */
export interface RequestRowActions {
  onApprove: (request: AccessRequestRow) => void
  onReject: (request: AccessRequestRow) => void
}

interface Props {
  requests: AccessRequestRow[]
  actions?: RequestRowActions
  onSelect?: (request: AccessRequestRow) => void
}

function HeaderCell({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)] whitespace-nowrap">
      {children}
    </th>
  )
}

export default function RequestsTable({ requests, actions, onSelect }: Props) {
  const { t } = useTranslation()

  if (requests.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="📝" title={t('accessControl.requests.empty')} />
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-surface border-b border-border-default">
            <HeaderCell>{t('accessControl.requests.created')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.plate')}</HeaderCell>
            <HeaderCell>{t('accessControl.requests.apartment')}</HeaderCell>
            <HeaderCell>{t('accessControl.requests.relation')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.status')}</HeaderCell>
            <HeaderCell>{t('accessControl.requests.reviewedAt')}</HeaderCell>
            <HeaderCell>{t('accessControl.requests.comment')}</HeaderCell>
            {actions && <HeaderCell>{t('common.actions')}</HeaderCell>}
          </tr>
        </thead>
        <tbody>
          {requests.map((r, idx) => {
            const isLast = idx === requests.length - 1
            return (
              <tr
                key={r.id}
                onClick={() => onSelect?.(r)}
                className={cn(
                  'transition-colors duration-100',
                  !isLast && 'border-b border-border-default',
                  onSelect && 'cursor-pointer hover:bg-bg-surface',
                )}
              >
                <td className="px-3 py-2.5 text-[13px] text-text-secondary whitespace-nowrap">
                  {formatDateTime(r.created_at)}
                </td>
                <td className="px-3 py-2.5 text-[13px] font-mono text-text-primary whitespace-nowrap">
                  {r.plate_number_original ?? r.plate_number_normalized ?? '—'}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary">#{r.apartment_id}</td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary">
                  {r.relation_type ?? '—'}
                </td>
                <td className="px-3 py-2.5">
                  <AccessStatusBadge status={r.status} />
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary whitespace-nowrap">
                  {formatDateTime(r.reviewed_at)}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-muted max-w-[220px] truncate">
                  {r.review_comment ?? '—'}
                </td>
                {actions && (
                  <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                    {r.status === 'pending' ? (
                      <div className="flex flex-wrap gap-1.5">
                        <Button size="sm" onClick={() => actions.onApprove(r)}>
                          {t('accessControl.actions.approve')}
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => actions.onReject(r)}>
                          {t('accessControl.actions.reject')}
                        </Button>
                      </div>
                    ) : (
                      <span className="text-[13px] text-text-muted">—</span>
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
