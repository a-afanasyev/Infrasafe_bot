import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import FormSection from './FormSection'
import { DASH, fmtDateOnly, fmtInstant, isHttpUrl } from '../../utils/elevatorsFormat'
import type { ElevatorDetail } from '../../types/elevators'

/**
 * Вкладка «Паспорт»: все поля read-only + действия manager (Редактировать,
 * Ввести в эксплуатацию — если не введён, Архивировать — если не в архиве).
 */
interface Props {
  elevator: ElevatorDetail
  canWrite: boolean
  onCommission: () => void
  onArchive: () => void
  commissionPending: boolean
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] uppercase tracking-wider text-text-muted">{label}</span>
      <span className="text-[13px] text-text-primary break-words">{value ?? DASH}</span>
    </div>
  )
}

const dash = (v: string | number | null | undefined) => (v === null || v === undefined || v === '' ? DASH : String(v))

/** Ссылка на акт — кликабельна только для http(s); `javascript:` и прочее — текстом. */
function ActUrl({ url }: { url: string | null }) {
  if (!url) return DASH
  if (!isHttpUrl(url)) return <>{url}</>
  return (
    <a href={url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">{url}</a>
  )
}

export default function ElevatorPassportTab({ elevator: e, canWrite, onCommission, onArchive, commissionPending }: Props) {
  const { t } = useTranslation()
  const yesNo = (v: boolean) => (v ? t('elevators.requests.yes') : t('elevators.requests.no'))
  const isArchived = e.archived_at !== null

  return (
    <div className="flex flex-col gap-4">
      {canWrite && !isArchived && (
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to={`/dashboard/elevators/${e.id}/edit`}>{t('elevators.actions.edit')}</Link>
          </Button>
          {!e.is_commissioned && (
            <Button size="sm" onClick={onCommission} disabled={commissionPending}>
              {t('elevators.actions.commission')}
            </Button>
          )}
          <Button size="sm" variant="destructive" onClick={onArchive}>
            {t('elevators.actions.archive')}
          </Button>
        </div>
      )}

      <FormSection title={t('elevators.form.sectionRequired')}>
        <Row label={t('elevators.form.building')} value={e.building_address} />
        <Row label={t('elevators.form.yard')} value={dash(e.yard_name)} />
        <Row label={t('elevators.form.entrance')} value={e.entrance_number} />
        <Row label={t('elevators.form.elevatorNumber')} value={e.elevator_number} />
        <Row label={t('elevators.form.passportNumber')} value={e.passport_number} />
        <Row label={t('elevators.form.manufacturer')} value={e.manufacturer} />
        <Row label={t('elevators.form.serialNumber')} value={e.serial_number} />
      </FormSection>

      <FormSection title={t('elevators.form.sectionPassport')}>
        <Row label={t('elevators.form.factoryNumber')} value={dash(e.factory_number)} />
        <Row label={t('elevators.form.model')} value={dash(e.model)} />
        <Row label={t('elevators.form.productionYear')} value={dash(e.production_year)} />
        <Row label={t('elevators.form.capacityKg')} value={dash(e.capacity_kg)} />
        <Row label={t('elevators.form.floorsServed')} value={dash(e.floors_served)} />
        <Row
          label={t('elevators.detail.commissionedAt')}
          value={e.is_commissioned ? fmtDateOnly(e.commissioned_at) : t('elevators.detail.notCommissioned')}
        />
        <Row label={t('elevators.detail.publicCode')} value={e.public_code} />
        <Row label={t('elevators.form.isPublic')} value={yesNo(e.is_public)} />
        <Row label={t('elevators.detail.version')} value={e.version} />
      </FormSection>

      <FormSection title={t('elevators.form.sectionContract')}>
        <Row label={t('elevators.form.serviceOrgName')} value={dash(e.service_org_name)} />
        <Row label={t('elevators.form.serviceOrgPhone')} value={dash(e.service_org_phone)} />
        <Row label={t('elevators.form.contractNumber')} value={dash(e.contract_number)} />
        <Row label={t('elevators.form.contractUntil')} value={fmtDateOnly(e.contract_until)} />
      </FormSection>

      <FormSection title={t('elevators.form.sectionCert')}>
        <Row label={t('elevators.form.certNumber')} value={dash(e.cert_number)} />
        <Row label={t('elevators.form.certValidUntil')} value={fmtDateOnly(e.cert_valid_until)} />
        <Row label={t('elevators.form.certActUrl')} value={<ActUrl url={e.cert_act_url} />} />
      </FormSection>

      <FormSection title={t('elevators.form.sectionDowntime')}>
        <Row label={t('elevators.form.downtimeReason')} value={dash(e.downtime_reason)} />
        <Row label={t('elevators.form.sparePartExpectedOn')} value={fmtDateOnly(e.spare_part_expected_on)} />
        <Row label={t('elevators.form.publishDowntimeDetails')} value={yesNo(e.publish_downtime_details)} />
        {isArchived && (
          <>
            <Row label={t('elevators.archivedBadge')} value={fmtInstant(e.archived_at)} />
            <Row label={t('elevators.detail.archivedReason')} value={dash(e.archived_reason)} />
          </>
        )}
      </FormSection>
    </div>
  )
}
