import { useTranslation } from 'react-i18next'
import type { ResidentApartment } from '../../types/api'
import { formatDate as fmtDate } from '../../i18n/formatters'
import { cn } from '@/lib/utils'

interface Props {
  apartments: ResidentApartment[]
}

const STATUS_COLORS: Record<string, string> = {
  approved: 'var(--emerald)',
  pending: 'var(--amber)',
  rejected: 'var(--red)',
}

/** Адрес привязки: «двор · дом · кв. N». Двор и дом выводятся ИЗ квартиры —
 *  собственных полей у привязки нет, поэтому у жителя с двумя квартирами в
 *  разных дворах будет два разных двора, и это норма. */
function buildAddress(a: ResidentApartment, aptShort: string): string {
  const parts: string[] = []
  if (a.yard_name) parts.push(a.yard_name)
  if (a.building_address) parts.push(a.building_address)
  parts.push(`${aptShort} ${a.apartment_number}`)
  return parts.join(' · ')
}

export default function ResidentApartmentsList({ apartments }: Props) {
  const { t } = useTranslation()

  if (apartments.length === 0) {
    return (
      <div className="text-[13px] text-text-muted">{t('residents.noApartments')}</div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {apartments.map(a => {
        const color = STATUS_COLORS[a.status] ?? 'var(--text-muted)'
        return (
          <div
            key={a.id}
            className="border border-border-default rounded-sm p-3 flex flex-col gap-1.5"
          >
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[13px] text-text-primary font-[family-name:var(--font-display)]">
                {buildAddress(a, t('residents.aptShort'))}
              </span>
              {a.is_primary && (
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-accent/15 text-accent">
                  {t('residents.primary')}
                </span>
              )}
              <span className={cn(
                'text-[11px] font-semibold px-2 py-0.5 rounded-full',
                a.is_owner ? 'bg-emerald/[.13] text-emerald' : 'bg-blue/[.13] text-blue',
              )}>
                {a.is_owner ? t('residents.owner') : t('residents.tenant')}
              </span>
              <span
                className="text-[11px] font-semibold px-2 py-0.5 rounded-full ml-auto"
                style={{ background: `color-mix(in srgb, ${color} 13%, transparent)`, color }}
              >
                {t(`residents.bindingStatus.${a.status}`, a.status)}
              </span>
            </div>
            <div className="text-[11px] text-text-muted font-[family-name:var(--font-display)]">
              {a.requested_at && t('residents.requestedAt', { date: fmtDate(a.requested_at, { dateStyle: 'short' }) })}
              {a.reviewed_at && ` · ${t('residents.reviewedAt', { date: fmtDate(a.reviewed_at, { dateStyle: 'short' }) })}`}
            </div>
            {a.admin_comment && (
              <div className="text-[12px] text-text-secondary italic">
                {a.admin_comment}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
