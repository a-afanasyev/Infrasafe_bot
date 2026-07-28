import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import type { ResidentListItem } from '../../types/api'
import { AVATAR_GRADIENTS, getInitials } from '../../utils/employeeUtils'
import { ResidentAccountBadge, ResidentVerificationBadge } from './ResidentStatusBadge'

interface Props {
  resident: ResidentListItem
}

export default function ResidentCard({ resident }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const name = [resident.first_name, resident.last_name].filter(Boolean).join(' ') || t('residents.noName')
  const isBlocked = resident.status === 'blocked'

  return (
    <div
      onClick={() => navigate(`/dashboard/residents/${resident.id}`)}
      className="bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-3 cursor-pointer transition-colors hover:border-accent"
    >
      <div className="flex items-start gap-3">
        <div
          className="w-11 h-11 rounded-full flex items-center justify-center text-white text-sm font-bold font-[family-name:var(--font-display)] shrink-0"
          style={{
            background: AVATAR_GRADIENTS[resident.id % AVATAR_GRADIENTS.length],
            opacity: isBlocked ? 0.5 : 1,
          }}
        >
          {getInitials(resident.first_name, resident.last_name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-[family-name:var(--font-display)] font-semibold text-sm text-text-primary truncate">
            {name}
          </div>
          {resident.phone && (
            <div className="text-xs text-text-muted font-[family-name:var(--font-mono)] mt-0.5">
              {resident.phone}
            </div>
          )}
        </div>
      </div>

      <div className="text-[13px] text-text-secondary leading-relaxed min-h-[18px]">
        {resident.primary_address ?? (
          <span className="text-text-muted">{t('residents.noAddress')}</span>
        )}
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <ResidentAccountBadge status={resident.status} />
        <ResidentVerificationBadge status={resident.verification_status} />
        <span className="text-[11px] text-text-muted ml-auto font-[family-name:var(--font-mono)]">
          {t('residents.apartmentsCount', { count: resident.apartments_count })}
        </span>
      </div>
    </div>
  )
}
