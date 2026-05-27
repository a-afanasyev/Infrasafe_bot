import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useEffect } from 'react'
import { toast } from 'sonner'
import { twaClient } from '../../twaClient'
import { tCategory, tStatus } from '../../../i18n/apiMaps'
import { getErrorMessage } from '../../utils/errors'
import StatusBadge from '../../components/StatusBadge'
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
}

export default function TaskDetailPage() {
  const { number } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showBackButton, haptic } = useTelegramSDK()

  useEffect(() => {
    return showBackButton(() => navigate(-1))
  }, [showBackButton, navigate])

  const { data: request, isLoading } = useQuery({
    queryKey: ['request', number],
    queryFn: () => twaClient.get(`/api/v2/requests/${number}`).then(r => r.data),
    enabled: !!number,
  })

  const statusMutation = useMutation({
    mutationFn: (newStatus: string) => twaClient.patch(`/api/v2/requests/${number}`, { status: newStatus }),
    onSuccess: () => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['request', number] })
      queryClient.invalidateQueries({ queryKey: ['executor-tasks'] })
    },
    onError: (err: unknown) => {
      haptic('notification')
      toast.error(getErrorMessage(err, 'Не удалось изменить статус'))
    },
  })

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

      {actions.length > 0 && (
        <div className="fixed bottom-16 left-4 right-4 flex gap-2">
          {actions.map((action) => (
            <button
              key={action.target}
              onClick={() => statusMutation.mutate(action.target)}
              disabled={statusMutation.isPending}
              className={`flex-1 text-white py-3 rounded-xl text-[13px] font-semibold disabled:opacity-50 ${action.color}`}
            >
              {t(action.label)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
