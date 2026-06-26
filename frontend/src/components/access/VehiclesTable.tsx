import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { VehicleRow } from '../../types/access'
import { AccessStatusBadge } from './AccessBadges'
import EmptyState from '../shared/EmptyState'

/**
 * Таблица базы автомобилей (экран менеджера). Клик по строке → деталь авто
 * (связи с квартирами + последние события).
 */
interface Props {
  vehicles: VehicleRow[]
  onRowClick?: (vehicle: VehicleRow) => void
}

function HeaderCell({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)] whitespace-nowrap">
      {children}
    </th>
  )
}

export default function VehiclesTable({ vehicles, onRowClick }: Props) {
  const { t } = useTranslation()

  if (vehicles.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon="🚙" title={t('accessControl.vehicles.empty')} />
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-surface border-b border-border-default">
            <HeaderCell>{t('accessControl.vehicles.plate')}</HeaderCell>
            <HeaderCell>{t('accessControl.vehicles.brandModel')}</HeaderCell>
            <HeaderCell>{t('accessControl.vehicles.color')}</HeaderCell>
            <HeaderCell>{t('accessControl.vehicles.class')}</HeaderCell>
            <HeaderCell>{t('accessControl.vehicles.apartments')}</HeaderCell>
            <HeaderCell>{t('accessControl.columns.status')}</HeaderCell>
          </tr>
        </thead>
        <tbody>
          {vehicles.map((v, idx) => {
            const isLast = idx === vehicles.length - 1
            const brandModel = [v.brand, v.model].filter(Boolean).join(' ') || '—'
            return (
              <tr
                key={v.id}
                onClick={() => onRowClick?.(v)}
                className={cn(
                  'transition-colors duration-100',
                  !isLast && 'border-b border-border-default',
                  onRowClick && 'cursor-pointer hover:bg-bg-surface',
                )}
              >
                <td className="px-3 py-2.5 text-[13px] font-mono font-semibold text-text-primary whitespace-nowrap">
                  {v.plate_number_original || v.plate_number_normalized}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-primary">{brandModel}</td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary">{v.color ?? '—'}</td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary">
                  {v.vehicle_class ?? '—'}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-text-secondary">
                  {v.apartments.length > 0
                    ? v.apartments.map((a) => a.apartment_id).join(', ')
                    : '—'}
                </td>
                <td className="px-3 py-2.5">
                  <AccessStatusBadge status={v.status} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
