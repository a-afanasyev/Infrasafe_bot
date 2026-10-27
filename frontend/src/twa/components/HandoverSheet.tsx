import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { twaClient } from '../twaClient'
import { tSpecialization } from '../../i18n/apiMaps'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { notifyError } from '../utils/errors'

interface Candidate {
  id: number
  name: string
  specializations: string[]
  open_requests: number
}

interface Props {
  requestNumber: string
  onClose: () => void
}

/**
 * Инженер передаёт «Инженерный разбор» мастеру: все одобренные исполнители
 * со специализациями и открытой нагрузкой. Передача — тот же PATCH
 * {executor_id}, что у менеджера (канон пускает инженера только на эту категорию).
 */
export default function HandoverSheet({ requestNumber, onClose }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()

  const { data: candidates, isLoading } = useQuery({
    queryKey: ['twa', 'handover-candidates', requestNumber],
    queryFn: () =>
      twaClient.get<Candidate[]>(`/api/v2/requests/${requestNumber}/handover-candidates`).then((r) => r.data),
  })

  const handover = useMutation({
    mutationFn: (executorId: number) =>
      twaClient.patch(`/api/v2/requests/${requestNumber}`, { executor_id: executorId }),
    onSuccess: () => {
      haptic('notification')
      toast.success(t('twa.exec.handover.done'))
      // Заявка больше не наша — карточку не перечитывать (был бы 403).
      queryClient.removeQueries({ queryKey: ['twa', 'request', requestNumber] })
      queryClient.invalidateQueries({ queryKey: ['twa', 'executor-tasks'] })
      navigate('/twa/exec', { replace: true })
    },
    onError: (err: unknown) => {
      haptic('notification')
      notifyError(err, t('twa.exec.handover.failed'))
    },
  })

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end" onClick={onClose}>
      <div
        className="w-full bg-white dark:bg-gray-800 rounded-t-2xl p-4 pb-6 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-semibold text-[15px] text-gray-900 dark:text-gray-100 mb-3">
          {t('twa.exec.handover.title')}
        </h3>
        {isLoading && <p className="text-[13px] text-gray-400">{t('common.loading')}</p>}
        {candidates?.length === 0 && <p className="text-[13px] text-gray-400">{t('twa.exec.handover.empty')}</p>}
        <div className="flex flex-col gap-2 mb-3">
          {candidates?.map((c) => (
            <button
              key={c.id}
              onClick={() => handover.mutate(c.id)}
              disabled={handover.isPending}
              className="text-left bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-3 disabled:opacity-50"
            >
              <div className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">{c.name}</div>
              <div className="text-[12px] text-gray-500">
                {c.specializations.map((s) => tSpecialization(s, t)).join(', ') || t('twa.exec.handover.noSpecialization')}
                {' · '}
                {t('twa.exec.handover.load', { count: c.open_requests })}
              </div>
            </button>
          ))}
        </div>
        <button
          onClick={onClose}
          className="w-full py-3 rounded-xl text-[13px] font-semibold bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
        >
          {t('common.cancel')}
        </button>
      </div>
    </div>
  )
}
