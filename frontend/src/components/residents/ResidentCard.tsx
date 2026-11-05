import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usePersonName } from '../../hooks/usePersonName'
import { useNavigate } from 'react-router'
import { useRequestResidentPhone, useSendRegistrationVideo } from '../../hooks/useResidents'
import type { ResidentListItem } from '../../types/api'
import { AVATAR_GRADIENTS, getInitials } from '../../utils/employeeUtils'
import { formatDate } from '../../utils/timezone'
import { BotBlockedBadge, ResidentAccountBadge, ResidentVerificationBadge } from './ResidentStatusBadge'
import { residentTone, type ResidentTone } from './residentTone'

const TINT = (color: string, pct = 8) => `color-mix(in srgb, ${color} ${pct}%, var(--color-bg-card))`

/** Фон и контур карточки по residentTone; одобренные — как раньше. */
const TONE_STYLE: Record<ResidentTone, { background?: string; borderColor?: string }> = {
  botBlocked: { background: TINT('var(--red)'), borderColor: 'var(--red)' },
  incomplete: { borderColor: 'var(--red)' },
  submitted: { background: TINT('var(--blue)') },
  pending: { background: TINT('var(--amber)', 14) }, // жёлтый на 8% теряется в тёмной теме
  default: {},
}

/** Совпадает с RESEND_AFTER сервера (api/residents/registration_video.py). */
const VIDEO_RESEND_MS = 24 * 60 * 60 * 1000

interface Props {
  resident: ResidentListItem
}

export default function ResidentCard({ resident }: Props) {
  const { t } = useTranslation()
  const { full: fullName } = usePersonName()
  const navigate = useNavigate()
  const requestPhone = useRequestResidentPhone(resident.id)
  const sendVideo = useSendRegistrationVideo(resident.id)
  const [mountedAt] = useState(Date.now) // «сейчас» на момент показа карточки: окно — сутки

  const name = fullName(resident, t('residents.noName'))
  const isBlocked = resident.status === 'blocked'
  const tone = residentTone(resident)
  const videoSentAt = resident.registration_video_sent_at
  const videoSentRecently = !!videoSentAt && mountedAt - Date.parse(videoSentAt) < VIDEO_RESEND_MS

  return (
    <div
      onClick={() => navigate(`/dashboard/residents/${resident.id}`)}
      data-tone={tone}
      style={TONE_STYLE[tone]}
      className="h-full bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-3 cursor-pointer transition-colors hover:border-accent"
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
          {resident.phone ? (
            <div className="text-xs text-text-muted font-[family-name:var(--font-mono)] mt-0.5">
              {resident.phone}
            </div>
          ) : (
            <button
              type="button"
              onClick={e => {
                // Карточка целиком кликабельна (открывает жителя) — кнопка
                // не должна вести туда же.
                e.stopPropagation()
                requestPhone.mutate()
              }}
              disabled={requestPhone.isPending || requestPhone.isSuccess}
              className="text-xs text-accent hover:underline mt-0.5 block disabled:opacity-60 disabled:no-underline"
            >
              {requestPhone.isSuccess
                ? t('employees.phoneRequestSent')
                : `📱 ${t('employees.requestPhone')}`}
            </button>
          )}
          {/* Факт запроса хранится на сервере — переживает перезагрузку. */}
          {!resident.phone && !requestPhone.isSuccess && resident.phone_requested_at && (
            <div className="text-[11px] text-text-muted mt-0.5">
              {t('employees.phoneRequestedOn', { date: formatDate(resident.phone_requested_at) })}
            </div>
          )}
          {tone === 'incomplete' && (videoSentRecently ? (
            <div className="text-[11px] text-text-muted mt-0.5">
              {t('residents.registrationVideoSentOn', { date: formatDate(videoSentAt) })}
            </div>
          ) : (
            <button
              type="button"
              onClick={e => {
                e.stopPropagation()
                sendVideo.mutate()
              }}
              disabled={sendVideo.isPending}
              className="text-xs text-accent hover:underline mt-0.5 block disabled:opacity-60 disabled:no-underline"
            >
              {t('residents.registrationVideo')}
            </button>
          ))}
        </div>
      </div>

      <div className="text-[13px] text-text-secondary leading-relaxed min-h-[18px]">
        {resident.primary_address ?? (
          <span className="text-text-muted">{t('residents.noAddress')}</span>
        )}
      </div>

      <div className="mt-auto flex items-center gap-1.5 flex-wrap">
        <ResidentAccountBadge status={resident.status} phone={resident.phone} apartmentsCount={resident.apartments_count} />
        <ResidentVerificationBadge status={resident.verification_status} submitted={resident.documents_submitted} />
        {resident.bot_blocked && <BotBlockedBadge />}
        <span className="text-[11px] text-text-muted ml-auto font-[family-name:var(--font-mono)]">
          {t('residents.apartmentsCount', { count: resident.apartments_count })}
        </span>
      </div>
    </div>
  )
}
