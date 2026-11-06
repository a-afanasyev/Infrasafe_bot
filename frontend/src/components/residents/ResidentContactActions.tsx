import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useRequestResidentPhone, useSendRegistrationVideo } from '../../hooks/useResidents'
import type { ResidentListItem } from '../../types/api'
import { formatDate } from '../../utils/timezone'
import { residentTone } from './residentTone'

/** Совпадает с RESEND_AFTER сервера (api/residents/registration_video.py). */
const VIDEO_RESEND_MS = 24 * 60 * 60 * 1000

/**
 * Телефон или «Запросить номер», под ним «Видео о регистрации» — одинаково
 * в карточке и в строке таблицы. Карточка и строка целиком кликабельны
 * (открывают жителя), поэтому кнопки гасят всплытие клика.
 */
export default function ResidentContactActions({ resident }: { resident: ResidentListItem }) {
  const { t } = useTranslation()
  const requestPhone = useRequestResidentPhone(resident.id)
  const sendVideo = useSendRegistrationVideo(resident.id)
  const [mountedAt] = useState(Date.now) // «сейчас» на момент показа: окно — сутки

  const videoSentAt = resident.registration_video_sent_at
  const videoSentRecently = !!videoSentAt && mountedAt - Date.parse(videoSentAt) < VIDEO_RESEND_MS

  return (
    <>
      {resident.phone ? (
        <div className="text-xs text-text-muted font-[family-name:var(--font-mono)] mt-0.5">
          {resident.phone}
        </div>
      ) : (
        <button
          type="button"
          onClick={e => {
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
      {residentTone(resident) === 'incomplete' && (videoSentRecently ? (
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
    </>
  )
}
