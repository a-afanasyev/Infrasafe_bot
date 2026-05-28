import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useCallback, useEffect, useRef } from 'react'
import { twaClient } from '../../twaClient'
import { tCategory, tStatus } from '../../../i18n/apiMaps'
import StatusBadge from '../../components/StatusBadge'
import MediaGallery from '../../components/MediaGallery'
import CommentThread from '../../components/CommentThread'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { ArrowLeft, User, MapPin, Calendar } from 'lucide-react'

export default function RequestDetailPage() {
  const { number } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showBackButton } = useTelegramSDK()

  // TWA-20: when the gallery lightbox is open, BackButton closes it first
  // instead of navigating off the page. Ref keeps the handler stable so we
  // don't re-register the Telegram BackButton on every lightbox toggle.
  const lightboxCloseRef = useRef<(() => void) | null>(null)
  // Stable so each gallery only republishes on its OWN lightbox toggle —
  // an unstable callback would make both galleries re-run their effect on
  // every render and clobber each other's close handler.
  const setLightboxClose = useCallback((close: (() => void) | null) => {
    lightboxCloseRef.current = close
  }, [])

  useEffect(() => {
    return showBackButton(() => {
      if (lightboxCloseRef.current) {
        lightboxCloseRef.current()
        return
      }
      navigate(-1)
    })
  }, [showBackButton, navigate])

  const { data: request, isLoading } = useQuery({
    queryKey: ['request', number],
    queryFn: () => twaClient.get(`/api/v2/requests/${number}`).then(r => r.data),
    enabled: !!number,
  })


  if (isLoading) return <div className="p-8 text-center text-gray-400">{t('common.loading')}</div>
  if (!request) return <div className="p-8 text-center text-gray-400">{t('common.error')}</div>

  const created = new Date(request.created_at)

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      {/* Header */}
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-emerald-500 text-[13px] mb-3">
        <ArrowLeft size={16} /> {t('common.back')}
      </button>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
        <div className="flex items-center justify-between mb-2">
          <span className="font-mono text-[12px] text-gray-400">{request.request_number}</span>
          <StatusBadge status={request.status} label={tStatus(request.status, t)} />
        </div>
        <h2 className="font-bold text-[16px] text-gray-900 dark:text-gray-100 mb-1">{tCategory(request.category, t)}</h2>
        <p className="text-[13px] text-gray-600 dark:text-gray-400">{request.description}</p>
      </div>

      {/* Info */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3 space-y-2">
        {request.address && (
          <div className="flex items-center gap-2 text-[12px]">
            <MapPin size={14} className="text-gray-400 shrink-0" />
            <span className="text-gray-600 dark:text-gray-400">{request.address}</span>
          </div>
        )}
        <div className="flex items-center gap-2 text-[12px]">
          <Calendar size={14} className="text-gray-400 shrink-0" />
          <span className="text-gray-600 dark:text-gray-400">
            {created.toLocaleDateString('ru-RU')} {created.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        {request.executor_name && (
          <div className="flex items-center gap-2 text-[12px]">
            <User size={14} className="text-gray-400 shrink-0" />
            <span className="text-gray-600 dark:text-gray-400">{request.executor_name}</span>
          </div>
        )}
      </div>

      {/* Clarification thread + completion report text */}
      {request.requested_materials && (
        <div className="bg-cyan-50 dark:bg-cyan-900/20 rounded-2xl p-4 border border-cyan-100 dark:border-cyan-800 mb-3">
          <p className="font-semibold text-[12px] text-cyan-800 dark:text-cyan-300 mb-1">{t('twa.exec.detail.materials')}</p>
          <p className="text-[12px] text-cyan-700 dark:text-cyan-400 whitespace-pre-line">{request.requested_materials}</p>
        </div>
      )}

      {request.notes && (
        <div className="bg-amber-50 dark:bg-amber-900/20 rounded-2xl p-4 border border-amber-100 dark:border-amber-800 mb-3">
          <p className="font-semibold text-[12px] text-amber-800 dark:text-amber-300 mb-1">{t('twa.detail.clarification')}</p>
          <p className="text-[12px] text-amber-700 dark:text-amber-400 whitespace-pre-line">{request.notes}</p>
        </div>
      )}

      {request.completion_report && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
          <p className="font-semibold text-[12px] text-gray-900 dark:text-gray-100 mb-1">{t('twa.detail.report')}</p>
          <p className="text-[12px] text-gray-600 dark:text-gray-400 whitespace-pre-line">{request.completion_report}</p>
        </div>
      )}

      {/* Media: request photos + (if any) the executor's completion report */}
      {number && (
        <>
          <MediaGallery
            requestNumber={number}
            kind="request"
            title={t('twa.detail.media')}
            onLightboxChange={setLightboxClose}
          />
          <MediaGallery
            requestNumber={number}
            kind="completion"
            title={t('twa.detail.photoReport')}
            onLightboxChange={setLightboxClose}
          />
        </>
      )}

      {/* Two-way clarification dialog */}
      {number && <CommentThread requestNumber={number} />}
    </div>
  )
}
