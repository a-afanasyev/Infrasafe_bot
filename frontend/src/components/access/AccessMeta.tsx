import { useTranslation } from 'react-i18next'
import type { ApplicantInfo, AddressInfo, ZoneRef } from '../../types/access'
import { formatAddress, formatApplicant, formatZones } from '../../utils/accessMeta'

/**
 * Общие блоки обогащённых деталей базы доступа: заявитель/житель, адрес квартиры
 * и зоны парковки. Переиспользуются в карточках авто, заявок и пропусков.
 * Чистые форматтеры живут в utils/accessMeta.ts.
 */

export function MetaField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-bold uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <span className="text-[13px] text-text-primary break-words">{value ?? '—'}</span>
    </div>
  )
}

/** Заявитель + адрес + зоны одним блоком (2 колонки). */
export function ApplicantAddressZones({
  applicant,
  address,
  zones,
  zonesLabel,
}: {
  applicant: ApplicantInfo | null | undefined
  address: AddressInfo | null | undefined
  zones: ZoneRef[] | null | undefined
  zonesLabel?: string
}) {
  const { t } = useTranslation()
  return (
    <div className="grid grid-cols-2 gap-3">
      <MetaField label={t('accessControl.meta.applicant')} value={formatApplicant(applicant)} />
      <MetaField label={t('accessControl.meta.address')} value={formatAddress(address, t)} />
      <MetaField
        label={zonesLabel ?? t('accessControl.meta.zone')}
        value={formatZones(zones)}
      />
    </div>
  )
}
