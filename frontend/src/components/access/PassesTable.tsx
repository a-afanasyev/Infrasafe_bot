import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { PassRow } from '../../types/access'
import { AccessStatusBadge } from './AccessBadges'
import { formatDateTime } from '../../utils/accessFormat'
import EmptyState from '../shared/EmptyState'

/**
 * Таблица временных пропусков (экран менеджера, пилот — taxi).
 */
interface Props {
  passes: PassRow[]
}

function HeaderCell({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)] whitespace-nowrap">
      {children}
    </th>
  )
}

export default function PassesTable({ passes }: Props) {
  const { t } = useTranslation()

  if (passes.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🎫" title={t('accessControl.passes.empty')} />
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-surface border-b border-border-default">
            <HeaderCell>{t('accessControl.passes.type')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.plate')}</HeaderCell>
            <HeaderCell>{t('accessControl.passes.apartment')}</HeaderCell>
            <HeaderCell>{t('accessControl.passes.validFrom')}</HeaderCell>
            <HeaderCell>{t('accessControl.passes.validUntil')}</HeaderCell>
            <HeaderCell>{t('accessControl.passes.entries')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.status')}</HeaderCell>
          </tr>
        </thead>
        <tbody>
          {passes.map((p, idx) => {
            const isLast = idx === passes.length - 1
            return (
              <tr
                key={p.id}
                className={cn('transition-colors duration-100', !isLast && 'border-b border-border-default')}
              >
                <td className="px-3 py-2.5 text-[13px] text-text-primary whitespace-nowrap">
                  {t(`accessControl.passes.passType.${p.pass_type}`, { defaultValue: p.pass_type })}
                </td>
                <td className="px-3 py-2.5 text-[13px] font-mono text-text-primary whitespace-nowrap">
                  {p.plate_number_original ?? p.plate_number_normalized ?? '—'}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary">#{p.apartment_id}</td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary whitespace-nowrap">
                  {formatDateTime(p.valid_from)}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary whitespace-nowrap">
                  {formatDateTime(p.valid_until)}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary whitespace-nowrap">
                  {p.used_entries}/{p.max_entries}
                </td>
                <td className="px-3 py-2.5">
                  <AccessStatusBadge status={p.status} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
