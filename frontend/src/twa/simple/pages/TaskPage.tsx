import { useCallback, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Check, Undo2, X } from 'lucide-react'
import { tCategory } from '../../../i18n/apiMaps'
import { useTaskCard } from '../api'
import { useBackTo } from '../hooks/useSimpleNav'
import { AuthPhoto } from '../components/Photo'
import { useResidentPhotoId } from '../hooks/useResidentPhoto'
import { CategoryIcon, StateChip } from '../components/TaskTile'
import { ErrorBlock, Loading, PRIMARY_BTN, SECONDARY_BTN, WaitManagerPlate } from '../components/Ui'
import { canComplete, returnReason } from '../model'
import { useCompletionQueue } from '../queue/CompletionQueue'

// Финальные статусы: действий исполнителя нет (сравниваем wire-значения API).
const CLOSED = new Set(['Выполнена', 'Исполнено', 'Принято', 'Отменена'])

/** Карточка заявки: фото жителя, адрес, весь текст, «Готово» / «Проблема». */
export default function TaskPage() {
  const { number = '' } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [zoom, setZoom] = useState(false)
  const { items: queued } = useCompletionQueue()

  const closeZoom = useCallback(() => {
    if (!zoom) return false
    setZoom(false)
    return true
  }, [zoom])
  useBackTo('/twa/s', closeZoom)

  const { data: task, isLoading, refetch } = useTaskCard(number)
  const photoId = useResidentPhotoId(number)

  if (!task) {
    return <main className="p-3">{isLoading ? <Loading /> : <ErrorBlock onRetry={() => void refetch()} />}</main>
  }

  const pending = queued.some((i) => i.requestNumber === number)
  const returned = task.status === 'Возвращена'
  const reason = returnReason(task)
  const canAct = !pending && !CLOSED.has(task.status)
  const completable = canComplete(task.status)
  const photoAlt = t('twa.simple.task.photoAlt')

  return (
    <main className="p-3 pb-[180px] flex flex-col gap-4">
      {photoId != null && (
        <button type="button" onClick={() => setZoom(true)} className="w-full rounded-2xl overflow-hidden bg-gray-200 dark:bg-gray-800">
          <AuthPhoto
            mediaId={photoId}
            alt={photoAlt}
            className="w-full h-64 object-cover"
            fallback={<div className="w-full h-64 animate-pulse" />}
          />
        </button>
      )}

      {pending && <StateChip state="pending" />}

      <div className="flex items-start gap-3">
        <span className="mt-1 text-gray-500 dark:text-gray-400"><CategoryIcon category={task.category} size={32} /></span>
        <h1 className="text-[28px] font-bold leading-tight break-words">{task.address?.trim() || tCategory(task.category, t)}</h1>
      </div>

      {returned && (
        <div role="alert" className="flex items-start gap-3 rounded-2xl bg-red-100 dark:bg-red-900/40 border-2 border-red-500 p-4 text-red-800 dark:text-red-200">
          <Undo2 size={28} className="shrink-0" aria-hidden />
          <p className="text-[20px] font-semibold break-words">
            {reason ? t('twa.simple.task.returned', { reason }) : t('twa.simple.status.returned')}
          </p>
        </div>
      )}

      {task.description && (
        <p className="text-[18px] leading-relaxed whitespace-pre-line break-words">{task.description}</p>
      )}

      <p className="text-[16px] text-gray-500 dark:text-gray-400">{t('twa.simple.task.number', { number: task.request_number })}</p>

      {canAct && (
        <div className="fixed bottom-0 left-0 right-0 z-40 bg-gray-100/95 dark:bg-gray-950/95 p-3 pb-[calc(12px+env(safe-area-inset-bottom))] flex flex-col gap-3">
          {completable ? (
            <button
              type="button"
              onClick={() => navigate(`/twa/s/task/${encodeURIComponent(number)}/done`)}
              className={`${PRIMARY_BTN} bg-emerald-600 text-white`}
            >
              <Check size={32} strokeWidth={3} aria-hidden /> {t('twa.simple.task.done')}
            </button>
          ) : (
            <WaitManagerPlate />
          )}
          <button
            type="button"
            onClick={() => navigate(`/twa/s/task/${encodeURIComponent(number)}/problem`)}
            className={`${SECONDARY_BTN} border-2 border-amber-500 text-amber-700 dark:text-amber-300 bg-white dark:bg-gray-900`}
          >
            <AlertTriangle size={26} aria-hidden /> {t('twa.simple.task.problem')}
          </button>
        </div>
      )}

      {zoom && photoId != null && (
        <div className="fixed inset-0 z-50 bg-black flex items-center justify-center" onClick={() => setZoom(false)}>
          <button
            type="button"
            aria-label={t('twa.simple.task.close')}
            className="absolute top-4 right-4 w-14 h-14 rounded-full bg-white/20 text-white flex items-center justify-center"
          >
            <X size={32} aria-hidden />
          </button>
          <AuthPhoto mediaId={photoId} alt={photoAlt} className="max-w-full max-h-full object-contain" fallback={null} />
        </div>
      )}
    </main>
  )
}
