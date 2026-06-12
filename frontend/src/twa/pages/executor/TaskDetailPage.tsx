import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useCallback, useEffect, useRef, useState } from 'react'
import { twaClient } from '../../twaClient'
import { tCategory, tStatus } from '../../../i18n/apiMaps'
import { notifyError } from '../../utils/errors'
import StatusBadge from '../../components/StatusBadge'
import MediaGallery from '../../components/MediaGallery'
import CommentThread from '../../components/CommentThread'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { ArrowLeft, MapPin, Calendar } from 'lucide-react'

const EXECUTOR_ACTIONS: Record<string, { label: string; target: string; color: string }[]> = {
  'Новая': [{ label: 'twa.exec.detail.takeWork', target: 'В работе', color: 'bg-emerald-500' }],
  'В работе': [
    { label: 'twa.exec.detail.complete', target: 'Выполнена', color: 'bg-emerald-500' },
    { label: 'twa.exec.detail.purchase', target: 'Закуп', color: 'bg-cyan-500' },
    { label: 'twa.exec.detail.clarify', target: 'Уточнение', color: 'bg-amber-500' },
  ],
  'Закуп': [{ label: 'twa.exec.detail.backToWork', target: 'В работе', color: 'bg-emerald-500' }],
  'Уточнение': [{ label: 'twa.exec.detail.backToWork', target: 'В работе', color: 'bg-emerald-500' }],
  // No "Выполнена" entry: the backend's executor transition table forbids
  // Выполнена → В работе (reopening a completed request is a manager action),
  // so a reopen button here would only ever 422.
}

export default function TaskDetailPage() {
  const { number } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showBackButton, haptic } = useTelegramSDK()

  // TWA-20: route BackButton to closing an open gallery lightbox first.
  const lightboxCloseRef = useRef<(() => void) | null>(null)
  const setLightboxClose = useCallback((close: (() => void) | null) => {
    lightboxCloseRef.current = close
  }, [])

  // Закуп / Уточнение need a text payload before the status flip.
  const [sheet, setSheet] = useState<'Закуп' | 'Уточнение' | null>(null)
  const [sheetText, setSheetText] = useState('')

  useEffect(() => {
    return showBackButton(() => {
      if (sheet) {
        setSheet(null)
        return
      }
      if (lightboxCloseRef.current) {
        lightboxCloseRef.current()
        return
      }
      navigate(-1)
    })
  }, [showBackButton, navigate, sheet])

  const { data: request, isLoading } = useQuery({
    queryKey: ['twa', 'request', number],
    queryFn: () => twaClient.get(`/api/v2/requests/${number}`).then(r => r.data),
    enabled: !!number,
  })

  const statusMutation = useMutation({
    mutationFn: (payload: { status: string; requested_materials?: string; notes?: string }) =>
      twaClient.patch(`/api/v2/requests/${number}`, payload),
    onSuccess: () => {
      haptic('notification')
      setSheet(null)
      setSheetText('')
      queryClient.invalidateQueries({ queryKey: ['twa', 'request', number] })
      queryClient.invalidateQueries({ queryKey: ['twa', 'executor-tasks'] })
    },
    onError: (err: unknown) => {
      haptic('notification')
      notifyError(err, 'Не удалось изменить статус')
    },
  })

  // Уточнение posts the question into the dialog thread (so the applicant can
  // answer back) and then moves the request to "Уточнение".
  const clarifyMutation = useMutation({
    mutationFn: async (body: string) => {
      await twaClient.post(`/api/v2/requests/${number}/comments`, { text: body })
      await twaClient.patch(`/api/v2/requests/${number}`, { status: 'Уточнение' })
    },
    onSuccess: () => {
      haptic('notification')
      setSheet(null)
      setSheetText('')
      queryClient.invalidateQueries({ queryKey: ['twa', 'request', number] })
      queryClient.invalidateQueries({ queryKey: ['twa', 'executor-tasks'] })
      queryClient.invalidateQueries({ queryKey: ['twa', 'comments', number] })
    },
    onError: (err: unknown) => {
      haptic('notification')
      notifyError(err, 'Не удалось отправить уточнение')
    },
  })

  const submitSheet = () => {
    const text = sheetText.trim()
    if (!text) return
    if (sheet === 'Закуп') {
      statusMutation.mutate({ status: 'Закуп', requested_materials: text })
    } else if (sheet === 'Уточнение') {
      clarifyMutation.mutate(text)
    }
  }

  if (isLoading) return <div className="p-8 text-center text-gray-400">{t('common.loading')}</div>
  if (!request) return <div className="p-8 text-center text-gray-400">{t('common.error')}</div>

  const actions = EXECUTOR_ACTIONS[request.status] || []
  const created = new Date(request.created_at)

  return (
    <div className="p-4 pb-24 min-h-screen bg-gray-50 dark:bg-gray-950">
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
            {created.toLocaleDateString()} {created.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>

      {request.requested_materials && (
        <div className="bg-cyan-50 dark:bg-cyan-900/20 rounded-2xl p-4 border border-cyan-100 dark:border-cyan-800 mb-3">
          <p className="font-semibold text-[12px] text-cyan-800 dark:text-cyan-300 mb-1">{t('twa.exec.detail.materials')}</p>
          <p className="text-[12px] text-cyan-700 dark:text-cyan-400">{request.requested_materials}</p>
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
          <CommentThread requestNumber={number} />
        </>
      )}

      {actions.length > 0 && (
        <div className="fixed bottom-16 left-4 right-4 flex gap-2">
          {actions.map((action) => (
            <button
              key={action.target}
              onClick={() => {
                // TWA-25: "Выполнена" goes through the completion-report page
                // (textarea + photo report) instead of a blind status flip —
                // that's the only path that reaches /twa/exec/report/:n.
                if (action.target === 'Выполнена') {
                  navigate(`/twa/exec/report/${number}`)
                  return
                }
                // Закуп / Уточнение open a text sheet first (materials list /
                // clarification); the rest flip status directly.
                if (action.target === 'Закуп' || action.target === 'Уточнение') {
                  setSheetText('')
                  setSheet(action.target)
                  return
                }
                statusMutation.mutate({ status: action.target })
              }}
              disabled={statusMutation.isPending}
              className={`flex-1 text-white py-3 rounded-xl text-[13px] font-semibold disabled:opacity-50 ${action.color}`}
            >
              {t(action.label)}
            </button>
          ))}
        </div>
      )}

      {sheet && (
        <div
          className="fixed inset-0 z-50 bg-black/50 flex items-end"
          onClick={() => setSheet(null)}
        >
          <div
            className="w-full bg-white dark:bg-gray-800 rounded-t-2xl p-4 pb-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold text-[15px] text-gray-900 dark:text-gray-100 mb-3">
              {t(sheet === 'Закуп' ? 'twa.exec.detail.purchaseTitle' : 'twa.exec.detail.clarifyTitle')}
            </h3>
            <textarea
              autoFocus
              value={sheetText}
              onChange={(e) => setSheetText(e.target.value)}
              placeholder={t(sheet === 'Закуп' ? 'twa.exec.detail.purchasePlaceholder' : 'twa.exec.detail.clarifyPlaceholder')}
              className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] min-h-[100px] resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500 mb-3"
            />
            <div className="flex gap-2">
              <button
                onClick={() => setSheet(null)}
                className="flex-1 py-3 rounded-xl text-[13px] font-semibold bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={submitSheet}
                disabled={!sheetText.trim() || statusMutation.isPending || clarifyMutation.isPending}
                className="flex-1 py-3 rounded-xl text-[13px] font-semibold bg-emerald-500 text-white disabled:opacity-50"
              >
                {t('common.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
