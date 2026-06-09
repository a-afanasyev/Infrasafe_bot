import { useState, useEffect, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { tCategory } from '../../../i18n/apiMaps'
import { URGENCIES } from '../../../constants'
import { notifyError } from '../../utils/errors'
import PhotoUploader from '../../components/PhotoUploader'

const CATEGORIES = ['electricity', 'plumbing', 'heating', 'ventilation', 'elevator', 'cleaning', 'landscaping', 'security', 'internet_tv', 'other']
// TASK 17: urgency — канон-ключи, шлём как есть (URGENCIES из общего constants).
// Backend (settings.REQUEST_CATEGORIES) expects Russian strings — map TWA i18n keys to API values.
const CATEGORY_API_MAP: Record<string, string> = {
  electricity: 'Электрика',
  plumbing: 'Сантехника',
  heating: 'Отопление',
  ventilation: 'Вентиляция',
  elevator: 'Лифт',
  cleaning: 'Уборка',
  landscaping: 'Благоустройство',
  security: 'Безопасность',
  internet_tv: 'Интернет/ТВ',
  other: 'Другое',
}

type AddressType = 'yard' | 'building' | 'apartment'

interface AddressItem {
  id: number
  label: string
}
interface RequestAddresses {
  yards: AddressItem[]
  buildings: AddressItem[]
  apartments: AddressItem[]
}

const EMPTY_ADDRESSES: RequestAddresses = { yards: [], buildings: [], apartments: [] }

export default function CreatePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic, showBackButton } = useTelegramSDK()

  // TWA-13 + план «Обходчик»: draft версионирован (v2) — структурный
  // {addressType, addressId} несовместим со старым {apartmentId, address}.
  // Старый ключ не читаем; восстановленный адрес ревалидируем по
  // /profile/request-addresses.
  const DRAFT_KEY = 'twa.create.draft.v2'
  type Draft = {
    step: number
    category: string
    addressType: AddressType | null
    addressId: number | null
    addressLabel: string
    description: string
    urgency: string
  }
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

  // Telegram BackButton for wizard steps
  const goBack = useCallback(() => {
    if (step > 0) setStep(s => s - 1)
    else navigate(-1)
  }, [step, navigate])

  useEffect(() => {
    if (step > 0) return showBackButton(goBack)
  }, [step, showBackButton, goBack])
  const [category, setCategory] = useState<string>(draft.category ?? '')
  const [addressType, setAddressType] = useState<AddressType | null>(draft.addressType ?? null)
  const [addressId, setAddressId] = useState<number | null>(draft.addressId ?? null)
  const [addressLabel, setAddressLabel] = useState<string>(draft.addressLabel ?? '')
  const [description, setDescription] = useState<string>(draft.description ?? '')
  const [urgency, setUrgency] = useState<string>(draft.urgency ?? 'low')
  const [photos, setPhotos] = useState<File[]>([])

  // Persist text-field draft on every change so a backgrounded WebApp can
  // resume where the user left off.
  useEffect(() => {
    try {
      sessionStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({ step, category, addressType, addressId, addressLabel, description, urgency } satisfies Draft)
      )
    } catch {}
  }, [step, category, addressType, addressId, addressLabel, description, urgency])
  // TWA-16: track per-photo upload progress.
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null)

  const { data: addresses = EMPTY_ADDRESSES, isSuccess: addressesLoaded } = useQuery<RequestAddresses>({
    queryKey: ['request-addresses'],
    queryFn: () => twaClient.get('/api/v2/profile/request-addresses').then(r => r.data),
  })

  // TWA-22 + план «Обходчик»: draft, восстановленный из sessionStorage, может
  // ссылаться на адрес, к которому житель больше не имеет доступа (изменился
  // между сессиями). Как только свежие наборы загрузились — сбрасываем
  // невалидный выбор и возвращаем мастер к шагу адреса.
  useEffect(() => {
    if (!addressesLoaded || addressType == null || addressId == null) return
    const pool: AddressItem[] =
      addressType === 'apartment' ? addresses.apartments
      : addressType === 'building' ? addresses.buildings
      : addresses.yards
    const stillValid = pool.some((a) => a.id === addressId)
    if (!stillValid) {
      setAddressType(null)
      setAddressId(null)
      setAddressLabel('')
      setStep(s => Math.min(s, 1))
      toast.info(t('twa.create.addressChanged'))
    }
  }, [addressesLoaded, addresses, addressType, addressId, t])

  function selectAddress(type: AddressType, item: AddressItem) {
    setAddressType(type)
    setAddressId(item.id)
    setAddressLabel(item.label)
    haptic('selection')
    setStep(2)
  }

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
      // Структурный контракт: сервер сам формирует адрес/FK/source по
      // {address_type, address_id}. Клиент address/source НЕ шлёт.
      const res = await twaClient.post('/api/v2/requests', {
        category: CATEGORY_API_MAP[category] || category,
        address_type: addressType,
        address_id: addressId,
        description,
        urgency: urgency,
      })
      const requestNumber: string | undefined = res.data?.request_number
      let photoFailures: number[] = []
      if (requestNumber && photos.length > 0) {
        photoFailures = await uploadPhotos(requestNumber)
      }
      return { requestNumber, photoFailures }
    },
    onSuccess: ({ photoFailures }) => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['my-requests'] })
      if (photoFailures.length > 0) {
        toast.warning(
          `Заявка создана, но не загрузились фото №${photoFailures.join(', ')}`
        )
      } else if (photos.length > 0) {
        toast.success(`Заявка создана (фото: ${photos.length})`)
      } else {
        toast.success('Заявка создана')
      }
      setUploadProgress(null)
      try { sessionStorage.removeItem(DRAFT_KEY) } catch {}
      navigate('/twa/app/requests')
    },
    onError: (err: unknown) => {
      setUploadProgress(null)
      notifyError(err, 'Не удалось создать заявку')
    },
  })

  const hasAnyAddress = addresses.apartments.length > 0 || addresses.buildings.length > 0 || addresses.yards.length > 0

  const addressSection = (type: AddressType, emoji: string, items: AddressItem[]) =>
    items.length > 0 && (
      <div className="space-y-2">
        {items.map((a) => (
          <button key={`${type}-${a.id}`} onClick={() => selectAddress(type, a)}
            className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] text-left active:scale-[0.97] transition-transform">
            {emoji} {a.label}
          </button>
        ))}
      </div>
    )

  const steps = [
    // Step 0: Category
    <div key="cat" className="space-y-2">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.selectCategory')}</h2>
      <div className="grid grid-cols-2 gap-2">
        {CATEGORIES.map((c) => (
          <button key={c} onClick={() => { setCategory(c); haptic('selection'); setStep(1) }}
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] font-medium text-left active:scale-[0.97] transition-transform">
            {tCategory(c, t)}
          </button>
        ))}
      </div>
    </div>,
    // Step 1: Address (3 levels: apartments → buildings → yards)
    <div key="addr" className="space-y-3">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.selectAddress')}</h2>
      {!hasAnyAddress && (
        <div className="text-[13px] text-gray-500 dark:text-gray-400">{t('twa.create.noAddresses')}</div>
      )}
      {addressSection('apartment', '🏠', addresses.apartments)}
      {addressSection('building', '🏢', addresses.buildings)}
      {addressSection('yard', '🏘️', addresses.yards)}
    </div>,
    // Step 2: Description
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
        onClick={() => setStep(3)}
        className="w-full mt-3 bg-emerald-500 text-white py-3 rounded-xl font-medium disabled:opacity-40"
      >{t('twa.create.next')}</button>
    </div>,
    // Step 3: Photos (optional)
    <div key="photos">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.photo.add')}</h2>
      <PhotoUploader files={photos} onChange={setPhotos} maxFiles={5} />
      <button
        onClick={() => setStep(4)}
        className="w-full mt-3 bg-emerald-500 text-white py-3 rounded-xl font-medium"
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
    // Step 5: Confirm
    <div key="confirm">
      <h2 className="font-semibold text-[15px] mb-3">{t('twa.create.confirm')}</h2>
      <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 space-y-2 text-[13px]">
        <div><span className="text-gray-500">{t('twa.create.categoryLabel')}:</span> {tCategory(category, t)}</div>
        <div><span className="text-gray-500">{t('twa.create.addressLabel')}:</span> {addressLabel}</div>
        <div><span className="text-gray-500">{t('twa.create.descriptionLabel')}:</span> {description}</div>
        <div><span className="text-gray-500">{t('twa.create.urgencyLabel')}:</span> {t(`twa.create.urgency.${urgency}`)}</div>
      </div>
      <button
        onClick={() => createMutation.mutate()}
        disabled={createMutation.isPending || addressId == null}
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
      {/* Progress bar */}
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
