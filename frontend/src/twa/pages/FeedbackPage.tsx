import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { AlertTriangle, Lightbulb } from 'lucide-react'
import { twaClient } from '../twaClient'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { notifyError } from '../utils/errors'
import PhotoUploader from '../components/PhotoUploader'

const MIN_TEXT_LEN = 10
type FeedbackType = 'complaint' | 'wish'

export default function FeedbackPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { haptic, showBackButton } = useTelegramSDK()

  const [type, setType] = useState<FeedbackType | null>(null)
  const [text, setText] = useState('')
  const [photos, setPhotos] = useState<File[]>([])

  useEffect(() => showBackButton(() => navigate(-1)), [showBackButton, navigate])

  const submit = useMutation({
    mutationFn: async () => {
      if (!type) return // защита от вызова вне canSubmit; type обязателен
      const form = new FormData()
      form.append('type', type)
      form.append('text', text.trim())
      if (photos[0]) form.append('file', photos[0])
      // Не задаём Content-Type вручную — axios сам выставит multipart + boundary для FormData.
      await twaClient.post('/api/v2/feedback', form)
    },
    onSuccess: () => {
      haptic('notification')
      toast.success(t('twa.feedback.success'))
      navigate(-1)
    },
    onError: (err: unknown) => notifyError(err, t('twa.feedback.error')),
  })

  const canSubmit = !!type && text.trim().length >= MIN_TEXT_LEN && !submit.isPending

  const typeOptions: { value: FeedbackType; label: string; Icon: typeof AlertTriangle }[] = [
    { value: 'complaint', label: t('twa.feedback.complaint'), Icon: AlertTriangle },
    { value: 'wish', label: t('twa.feedback.wish'), Icon: Lightbulb },
  ]

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.feedback.title')}</h1>

      {/* Тип обращения */}
      <p className="font-semibold text-[13px] mb-2 text-gray-700 dark:text-gray-300">{t('twa.feedback.typeLabel')}</p>
      <div className="grid grid-cols-2 gap-2 mb-4">
        {typeOptions.map(({ value, label, Icon }) => (
          <button
            key={value}
            onClick={() => { setType(value); haptic('selection') }}
            className={`flex items-center justify-center gap-2 rounded-xl p-3 text-[13px] font-medium border transition-colors ${
              type === value
                ? 'bg-emerald-500 text-white border-emerald-500'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300'
            }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      {/* Текст */}
      <p className="font-semibold text-[13px] mb-2 text-gray-700 dark:text-gray-300">{t('twa.feedback.descriptionLabel')}</p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t('twa.feedback.descriptionPlaceholder')}
        className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] min-h-[120px] resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500 mb-4"
      />

      {/* Фото (необязательно) */}
      <p className="font-semibold text-[13px] mb-2 text-gray-700 dark:text-gray-300">{t('twa.feedback.photoOptional')}</p>
      <div className="mb-4">
        <PhotoUploader files={photos} onChange={setPhotos} maxFiles={1} accept="image/*" />
      </div>

      <button
        onClick={() => submit.mutate()}
        disabled={!canSubmit}
        className="w-full bg-emerald-500 text-white py-3 rounded-xl font-semibold disabled:opacity-40"
      >
        {submit.isPending ? t('common.loading') : t('twa.feedback.submit')}
      </button>
    </div>
  )
}
