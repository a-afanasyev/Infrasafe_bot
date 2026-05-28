import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { notifyError } from '../../utils/errors'
import PhotoUploader from '../../components/PhotoUploader'

export default function CompletionReport() {
  const { number } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()
  const [report, setReport] = useState('')
  const [photos, setPhotos] = useState<File[]>([])

  // Completion photos go through the same proxy as request photos but tagged
  // category=completion_photo, so the detail pages can show them in a separate
  // "Фотоотчёт" section. Best-effort: a per-photo failure is reported but
  // doesn't undo the completed status.
  async function uploadPhotos(requestNumber: string): Promise<number[]> {
    const failed: number[] = []
    for (let i = 0; i < photos.length; i++) {
      const form = new FormData()
      form.append('file', photos[i])
      form.append('request_number', requestNumber)
      form.append('category', 'completion_photo')
      try {
        await twaClient.post('/api/v2/media/upload', form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      } catch {
        failed.push(i + 1)
      }
    }
    return failed
  }

  const completeMutation = useMutation({
    mutationFn: async () => {
      await twaClient.patch(`/api/v2/requests/${number}`, {
        status: 'Выполнена',
        completion_report: report || undefined,
      })
      let failures: number[] = []
      if (number && photos.length > 0) failures = await uploadPhotos(number)
      return { failures }
    },
    onSuccess: ({ failures }) => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['executor-tasks'] })
      queryClient.invalidateQueries({ queryKey: ['request', number] })
      queryClient.invalidateQueries({ queryKey: ['media', number] })
      if (failures.length > 0) {
        toast.warning(`Заявка завершена, но не загрузились фото №${failures.join(', ')}`)
      }
      navigate('/twa/exec')
    },
    onError: (err: unknown) => {
      haptic('notification')
      notifyError(err, 'Не удалось завершить заявку')
    },
  })

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.report.title')}</h1>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-4">
        <p className="text-[12px] text-gray-500 mb-2">{t('twa.exec.report.description')}</p>
        <textarea
          value={report}
          onChange={(e) => setReport(e.target.value)}
          placeholder={t('twa.exec.report.placeholder')}
          className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] min-h-[100px] resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500"
        />
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-4">
        <p className="text-[12px] text-gray-500 mb-2">{t('twa.exec.report.photos')}</p>
        <PhotoUploader files={photos} onChange={setPhotos} />
      </div>

      <button
        onClick={() => completeMutation.mutate()}
        disabled={completeMutation.isPending}
        className="w-full bg-emerald-500 text-white py-3 rounded-xl font-semibold disabled:opacity-50"
      >
        {completeMutation.isPending ? t('common.loading') : t('twa.exec.report.submit')}
      </button>
    </div>
  )
}
