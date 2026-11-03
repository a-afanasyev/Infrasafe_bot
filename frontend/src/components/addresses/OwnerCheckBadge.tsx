import { useTranslation } from 'react-i18next'
import type { OwnerCheck } from '../../types/api'

/** Кто владелец лицевого счёта квартиры по Mening Uyim — информация менеджеру. */
export default function OwnerCheckBadge({ check }: { check?: OwnerCheck | null }) {
  const { t } = useTranslation()
  if (!check) return null
  return (
    <div className="text-[12px] text-text-secondary bg-bg-surface px-2.5 py-1 rounded-sm w-fit">
      {t(`ownerCheck.${check.status}`, { owner: check.owner_name ?? '', account: check.account_number ?? '' })}
    </div>
  )
}
