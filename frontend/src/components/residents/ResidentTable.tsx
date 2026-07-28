import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import type { ResidentListItem } from '../../types/api'
import { AVATAR_GRADIENTS, getInitials } from '../../utils/employeeUtils'
import EmptyState from '../shared/EmptyState'
import { ResidentAccountBadge, ResidentVerificationBadge } from './ResidentStatusBadge'

interface Props {
  residents: ResidentListItem[]
}

export default function ResidentTable({ residents }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const HEADERS = [
    t('residents.headerResident'),
    t('residents.headerAddress'),
    t('residents.headerApartments'),
    t('residents.headerVerification'),
    t('residents.headerStatus'),
  ]

  if (residents.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default p-10">
        <EmptyState icon="👥" title={t('residents.notFound')} subtitle={t('residents.notFoundDesc')} />
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-surface border-b border-border-default">
            {HEADERS.map(h => (
              <th
                key={h}
                className="px-4 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)]"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {residents.map(r => {
            const name = [r.first_name, r.last_name].filter(Boolean).join(' ') || t('residents.noName')
            return (
              <tr
                key={r.id}
                onClick={() => navigate(`/dashboard/residents/${r.id}`)}
                className="border-b border-border-default last:border-b-0 cursor-pointer hover:bg-bg-surface transition-colors"
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <div
                      className="w-8 h-8 rounded-full flex items-center justify-center text-white text-[11px] font-bold font-[family-name:var(--font-display)] shrink-0"
                      style={{
                        background: AVATAR_GRADIENTS[r.id % AVATAR_GRADIENTS.length],
                        opacity: r.status === 'blocked' ? 0.5 : 1,
                      }}
                    >
                      {getInitials(r.first_name, r.last_name)}
                    </div>
                    <div className="min-w-0">
                      <div className="text-[13px] text-text-primary truncate">{name}</div>
                      {r.phone && (
                        <div className="text-[11px] text-text-muted font-[family-name:var(--font-mono)]">
                          {r.phone}
                        </div>
                      )}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-[13px] text-text-secondary">
                  {r.primary_address ?? <span className="text-text-muted">{t('residents.noAddress')}</span>}
                </td>
                <td className="px-4 py-3 text-[13px] text-text-secondary font-[family-name:var(--font-mono)]">
                  {r.apartments_count}
                </td>
                <td className="px-4 py-3">
                  <ResidentVerificationBadge status={r.verification_status} />
                </td>
                <td className="px-4 py-3">
                  <ResidentAccountBadge status={r.status} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
