import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useEffect } from 'react'
import { twaClient } from '../../twaClient'
import { tCategory, tStatus } from '../../../i18n/apiMaps'
import StatusBadge from '../../components/StatusBadge'
import MediaGallery from '../../components/MediaGallery'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { ArrowLeft, User, MapPin, Calendar } from 'lucide-react'

export default function RequestDetailPage() {
  const { number } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showBackButton } = useTelegramSDK()

  useEffect(() => {
    return showBackButton(() => navigate(-1))
  }, [showBackButton, navigate])

  const { data: request, isLoading } = useQuery({
    queryKey: ['request', number],
    queryFn: () => twaClient.get(`/api/v2/requests/${number}`).then(r => r.data),
    enabled: !!number,
  })

  const { data: comments = [] } = useQuery({
    queryKey: ['comments', number],
    queryFn: () => twaClient.get(`/api/v2/requests/${number}/comments`).then(r => r.data),
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

      {/* Media */}
      {number && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
          <h3 className="font-semibold text-[13px] text-gray-900 dark:text-gray-100 mb-2">{t('twa.detail.media')}</h3>
          <MediaGallery requestNumber={number} />
        </div>
      )}

      {/* Comments */}
      {comments.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700">
          <h3 className="font-semibold text-[13px] text-gray-900 dark:text-gray-100 mb-2">{t('twa.detail.comments')}</h3>
          {comments.map((c: any) => (
            <div key={c.id} className="py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
              <p className="text-[12px] text-gray-600 dark:text-gray-400">{c.comment_text}</p>
              <span className="text-[10px] text-gray-400 mt-1 block">
                {new Date(c.created_at).toLocaleString('ru-RU')}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
