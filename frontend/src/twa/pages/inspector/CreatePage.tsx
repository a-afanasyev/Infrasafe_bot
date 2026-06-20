import { useState, useEffect, useCallback } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { tCategory } from '../../../i18n/apiMaps'
import { CATEGORIES, URGENCIES } from '../../../constants'
import { notifyError } from '../../utils/errors'
import PhotoUploader from '../../components/PhotoUploader'
import RoleSwitchButton from '../../components/RoleSwitchButton'

// FS-04: category — канон-EN-ключ из общего constants, шлём как есть.

interface Yard {
  id: number
  name: string
}
interface Building {
  id: number
  address: string
}

/**
 * Inspector create flow (план «Обходчик»). Одноцелевая роль: завести
 * building-level заявку с любого активного двора/дома (двор→дом). Сабмит
 * {address_type:"building", address_id} → POST /requests/inspector. Сервер
 * проверяет активность дома/двора; принадлежность не требуется. Post-submit —
 * сброс формы и остаёмся на /twa/inspector (НЕ уходим в applicant-раздел).
 */
const DRAFT_KEY = 'twa.create.inspector.draft'

type Draft = {
  step: number
  yardId: number | null
  buildingId: number | null
  buildingLabel: string
  category: string
  description: string
  urgency: string
}

export default function InspectorCreatePage() {
  const { t } = useTranslation()
  const { haptic, showBackButton } = useTelegramSDK()

  const loadDraft = (): Partial<Draft> => {
    try {
      const raw = sessionStorage.getItem(DRAFT_KEY)
      return raw ? (JSON.parse(raw) as Partial<Draft>) : {}
    } catch {
      return {}
    }
  }
  const draft = loadDraft()

  const [step, setStep] = useState<number>(draft.step ?? 0)
  const [yardId, setYardId] = useState<number | null>(draft.yardId ?? null)
  const [buildingId, setBuildingId] = useState<number | null>(draft.buildingId ?? null)
  const [buildingLabel, setBuildingLabel] = useState<string>(draft.buildingLabel ?? '')
  const [category, setCategory] = useState<string>(draft.category ?? '')
  const [description, setDescription] = useState<string>(draft.description ?? '')
  const [urgency, setUrgency] = useState<string>(draft.urgency ?? 'low')
  // Фото (File[]) не сериализуются в draft — живут только в текущей сессии.
  const [photos, setPhotos] = useState<File[]>([])
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null)

  const goBack = useCallback(() => {
    if (step > 0) setStep(s => s - 1)
  }, [step])
  useEffect(() => {
    if (step > 0) return showBackButton(goBack)
  }, [step, showBackButton, goBack])

  useEffect(() => {
    try {
      sessionStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({ step, yardId, buildingId, buildingLabel, category, description, urgency } satisfies Draft)
      )
    } catch {}
  }, [step, yardId, buildingId, buildingLabel, category, description, urgency])

  const { data: yards = [] } = useQuery<Yard[]>({
    queryKey: ['twa', 'inspector-yards'],
    queryFn: () => twaClient.get('/api/v2/addresses/yards').then(r => r.data),
  })

  const { data: buildings = [] } = useQuery<Building[]>({
    queryKey: ['twa', 'inspector-buildings', yardId],
    queryFn: () => twaClient.get(`/api/v2/addresses/yards/${yardId}/buildings`).then(r => r.data),
    enabled: yardId != null,
  })

  function resetForm() {
    setStep(0)
    setYardId(null)
    setBuildingId(null)
    setBuildingLabel('')
    setCategory('')
    setDescription('')
    setUrgency('low')
    setPhotos([])
    setUploadProgress(null)
    try { sessionStorage.removeItem(DRAFT_KEY) } catch {}
  }

  // Загрузка фото через прокси (как в applicant-flow): последовательно, любой
  // сбой отдельного файла репортится, но не откатывает уже созданную заявку.
  async function uploadPhotos(requestNumber: string): Promise<number[]> {
    const failedIdx: number[] = []
    setUploadProgress({ done: 0, total: photos.length })
    for (let i = 0; i < photos.length; i++) {
      const form = new FormData()
      form.append('file', photos[i])
      form.append('request_number', requestNumber)
      form.append('category', 'request_photo')
      try {
        await twaClient.post('/api/v2/media/upload', form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      } catch {
        failedIdx.push(i + 1)
      }
      setUploadProgress({ done: i + 1, total: photos.length })
    }
    return failedIdx
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      const res = await twaClient.post('/api/v2/requests/inspector', {
        category,
        address_type: 'building',
        address_id: buildingId,
        description,
        urgency,
      })
      const requestNumber = res.data?.request_number as string | undefined
      let photoFailures: number[] = []
      if (requestNumber && photos.length > 0) {
        photoFailures = await uploadPhotos(requestNumber)
      }
      return { requestNumber, photoFailures }
    },
    onSuccess: ({ photoFailures }) => {
      haptic('notification')
      if (photoFailures.length > 0) {
        toast.warning(`Заявка создана, не загрузились фото №${photoFailures.join(', ')}`)
      } else {
        toast.success(t('twa.create.submitted'))
      }
      // Остаёмся на /twa/inspector — просто сбрасываем форму для следующей заявки.
      resetForm()
    },
    onError: (err: unknown) => {
      setUploadProgress(null)
      notifyError(err, t('twa.create.submitFailed'))
    },
  })

  const steps = [
    // Step 0: Yard
    <div key="yard" className="space-y-2">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.inspector.selectYard')}</h2>
      {yards.length === 0 && (
        <div className="text-[13px] text-gray-500 dark:text-gray-400">{t('twa.inspector.noYards')}</div>
      )}
      {yards.map((y) => (
        <button key={y.id} onClick={() => { setYardId(y.id); setBuildingId(null); haptic('selection'); setStep(1) }}
          className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] text-left active:scale-[0.97] transition-transform">
          🏘️ {y.name}
        </button>
      ))}
    </div>,
    // Step 1: Building
    <div key="bld" className="space-y-2">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.inspector.selectBuilding')}</h2>
      {buildings.length === 0 && (
        <div className="text-[13px] text-gray-500 dark:text-gray-400">{t('twa.inspector.noBuildings')}</div>
      )}
      {buildings.map((b) => (
        <button key={b.id} onClick={() => { setBuildingId(b.id); setBuildingLabel(b.address); haptic('selection'); setStep(2) }}
          className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] text-left active:scale-[0.97] transition-transform">
          🏢 {b.address}
        </button>
      ))}
    </div>,
    // Step 2: Category
    <div key="cat" className="space-y-2">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.selectCategory')}</h2>
      <div className="grid grid-cols-2 gap-2">
        {CATEGORIES.map((c) => (
          <button key={c} onClick={() => { setCategory(c); haptic('selection'); setStep(3) }}
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] font-medium text-left active:scale-[0.97] transition-transform">
            {tCategory(c, t)}
          </button>
        ))}
      </div>
    </div>,
    // Step 3: Description
    <div key="desc">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.describe')}</h2>
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder={t('twa.create.descriptionPlaceholder')}
        className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] min-h-[120px] resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500"
      />
      <button
        disabled={!description.trim()}
        onClick={() => setStep(4)}
        className="w-full mt-3 bg-emerald-500 text-white py-3 rounded-xl font-medium disabled:opacity-40"
      >{t('twa.create.next')}</button>
    </div>,
    // Step 4: Urgency
    <div key="urg" className="space-y-2">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.selectUrgency')}</h2>
      {URGENCIES.map((u) => (
        <button key={u} onClick={() => { setUrgency(u); haptic('selection'); setStep(5) }}
          className={`w-full bg-white dark:bg-gray-800 border rounded-xl p-3 text-[13px] text-left active:scale-[0.97] transition-transform ${
            u === 'critical' ? 'border-red-300 dark:border-red-700' : 'border-gray-200 dark:border-gray-700'
          }`}>
          {t(`twa.create.urgency.${u}`)}
        </button>
      ))}
    </div>,
    // Step 5: Photos (optional)
    <div key="photos">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.photo.add')}</h2>
      <PhotoUploader files={photos} onChange={setPhotos} maxFiles={5} />
      <button
        onClick={() => setStep(6)}
        className="w-full mt-3 bg-emerald-500 text-white py-3 rounded-xl font-medium"
      >{t('twa.create.next')}</button>
    </div>,
    // Step 6: Confirm
    <div key="confirm">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.confirm')}</h2>
      <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 space-y-2 text-[13px]">
        <div><span className="text-gray-500">{t('twa.create.categoryLabel')}:</span> {tCategory(category, t)}</div>
        <div><span className="text-gray-500">{t('twa.create.addressLabel')}:</span> 🏢 {buildingLabel}</div>
        <div><span className="text-gray-500">{t('twa.create.descriptionLabel')}:</span> {description}</div>
        <div><span className="text-gray-500">{t('twa.create.urgencyLabel')}:</span> {t(`twa.create.urgency.${urgency}`)}</div>
        {photos.length > 0 && (
          <div><span className="text-gray-500">📸:</span> {photos.length}</div>
        )}
      </div>
      <button
        onClick={() => createMutation.mutate()}
        disabled={createMutation.isPending || buildingId == null}
        className="w-full mt-4 bg-emerald-500 text-white py-3 rounded-xl font-semibold disabled:opacity-50"
      >{createMutation.isPending ? t('common.loading') : t('twa.create.submit')}</button>
      {uploadProgress && uploadProgress.total > 0 && (
        <div className="mt-3 text-center text-[12px] text-gray-500 dark:text-gray-400">
          Загрузка фото {uploadProgress.done}/{uploadProgress.total}
        </div>
      )}
      {createMutation.isError && (
        <div className="mt-3 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-[12px]">
          {(() => {
            const err = createMutation.error as any
            const detail = err?.response?.data?.detail
            if (Array.isArray(detail)) return detail.map((d: any) => `${d.loc?.join('.')}: ${d.msg}`).join('; ')
            if (typeof detail === 'string') return detail
            return err?.message || t('common.error')
          })()}
        </div>
      )}
    </div>,
  ]

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <RoleSwitchButton to="applicant" />
      <RoleSwitchButton to="executor" />

      <div className="flex gap-1 mb-4">
        {steps.map((_, i) => (
          <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${i <= step ? 'bg-emerald-500' : 'bg-gray-200 dark:bg-gray-700'}`} />
        ))}
      </div>

      {step > 0 && (
        <button onClick={() => setStep(step - 1)} className="text-[13px] text-emerald-500 mb-3">
          ← {t('common.back')}
        </button>
      )}

      {steps[step]}
    </div>
  )
}
