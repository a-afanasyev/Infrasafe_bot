import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { useResident } from '../hooks/useResidents'
import ResidentApartmentsList from '../components/residents/ResidentApartmentsList'
import ResidentAccountActions from '../components/residents/ResidentAccountActions'
import AttachApartmentModal from '../components/residents/AttachApartmentModal'
import ResidentDocuments from '../components/residents/ResidentDocuments'
import ResidentVerificationActions from '../components/residents/ResidentVerificationActions'
import { ResidentAccountBadge, ResidentVerificationBadge } from '../components/residents/ResidentStatusBadge'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { AVATAR_GRADIENTS, getInitials } from '../utils/employeeUtils'
import { usePageTitle } from '../hooks/usePageTitle'
import { formatDate as fmtDate } from '../i18n/formatters'
import { Button } from '@/components/ui/button'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-3">
      <div className="text-xs font-bold text-text-muted uppercase tracking-wider">{title}</div>
      {children}
    </div>
  )
}

export default function ResidentDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: resident, isLoading, isError } = useResident(id ? Number(id) : null)
  const [attachOpen, setAttachOpen] = useState(false)

  const name = resident
    ? [resident.first_name, resident.last_name].filter(Boolean).join(' ') || t('residents.noName')
    : t('residents.noName')
  usePageTitle(name)

  if (isLoading) return <LoadingSpinner />
  if (isError || !resident) return (
    <div className="py-10 px-6 text-text-muted text-center">{t('residents.notFound')}</div>
  )

  const isBlocked = resident.status === 'blocked'

  return (
    <div className="p-5 px-6 flex flex-col gap-5 max-w-[820px]">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate(-1)}
        className="self-start px-0 text-text-muted"
      >
        {'←'} {t('common.back')}
      </Button>

      {/* Header */}
      <div className="bg-bg-card border border-border-default rounded-default p-6 flex gap-5 items-start">
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center text-white text-xl font-bold font-[family-name:var(--font-display)] shrink-0"
          style={{
            background: AVATAR_GRADIENTS[resident.id % AVATAR_GRADIENTS.length],
            opacity: isBlocked ? 0.5 : 1,
          }}
        >
          {getInitials(resident.first_name, resident.last_name)}
        </div>

        <div className="flex-1 min-w-0">
          <div className="font-[family-name:var(--font-display)] font-bold text-lg text-text-primary mb-1">
            {name}
          </div>
          {resident.phone && (
            <div className="text-[13px] text-text-muted font-[family-name:var(--font-mono)] mb-1">
              {resident.phone}
            </div>
          )}
          <div className="text-[11px] text-text-muted font-[family-name:var(--font-mono)] mb-3">
            {resident.username ? `@${resident.username} · ` : ''}TG {resident.telegram_id}
          </div>
          <div className="flex gap-2 flex-wrap">
            <ResidentAccountBadge status={resident.status} />
            <ResidentVerificationBadge status={resident.verification_status} />
            {/* Роли показываем только когда житель ещё и сотрудник: это
                объясняет, почему блокировка отсюда недоступна (PR-4). */}
            {resident.roles.filter(r => r !== 'applicant').map(r => (
              <span
                key={r}
                className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-violet/[.13] text-violet"
              >
                {t(`role.${r}`, r)}
              </span>
            ))}
          </div>
        </div>
      </div>

      <ResidentAccountActions resident={resident} />

      <Section title={t('residents.sectionApartments')}>
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setAttachOpen(true)}>
            {t('residents.attachApartment')}
          </Button>
        </div>
        <ResidentApartmentsList residentId={resident.id} apartments={resident.apartments} />
      </Section>

      {attachOpen && (
        <AttachApartmentModal
          residentId={resident.id}
          onClose={() => setAttachOpen(false)}
        />
      )}

      <Section title={t('residents.sectionDocuments')}>
        <ResidentDocuments residentId={resident.id} documents={resident.documents} />
      </Section>

      <Section title={t('residents.sectionVerification')}>
        <ResidentVerificationActions resident={resident} />
        {resident.latest_verification ? (
          <div className="flex flex-col gap-1.5 text-[13px] text-text-secondary">
            <div>
              {t('residents.verificationRecordStatus')}:{' '}
              <span className="text-text-primary">
                {t(`residents.verification.${resident.latest_verification.status}`, resident.latest_verification.status ?? '—')}
              </span>
            </div>
            {resident.latest_verification.requested_at && (
              <div className="text-[11px] text-text-muted">
                {t('residents.requestedAt', {
                  date: fmtDate(resident.latest_verification.requested_at, { dateStyle: 'short' }),
                })}
              </div>
            )}
            {resident.latest_verification.admin_notes && (
              <div className="italic">{resident.latest_verification.admin_notes}</div>
            )}
          </div>
        ) : (
          <div className="text-[13px] text-text-muted">{t('residents.noVerification')}</div>
        )}
      </Section>
    </div>
  )
}
