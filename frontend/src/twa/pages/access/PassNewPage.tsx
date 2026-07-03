import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { notifyError } from '../../utils/errors'
import ApartmentSelect from './ApartmentSelect'
import { useApartments } from './useApartments'
import {
  ACCESS_BASE,
  RESIDENT_PASS_TYPES,
  type ResidentPassType,
  type PassCreateResponse,
} from './types'

/**
 * Форма «Заказать пропуск» (POST /api/v1/access/passes).
 * Тело: { apartment_id, pass_type, valid_until, plate_number_original?, ... }.
 * zone_id не шлём — резолвится бэкендом; на 422 zone_not_resolved показываем
 * подсказку (в пилоте зона обычно одна, ошибка маловероятна).
 */
export default function PassNewPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic, showBackButton } = useTelegramSDK()

  const { data: apartments = [], isLoading: apartmentsLoading } = useApartments()

  const [apartmentId, setApartmentId] = useState<number | null>(null)
  const [passType, setPassType] = useState<ResidentPassType>('guest')
  const [plate, setPlate] = useState('')
  const [validUntil, setValidUntil] = useState('')
  // Одноразовый код гостя (§9.3): приходит только для guest-пропуска без номера.
  // Пока он показан — рендерим экран успеха с кодом вместо формы.
  const [oneTimeCode, setOneTimeCode] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => showBackButton(() => navigate(-1)), [showBackButton, navigate])

  useEffect(() => {
    if (apartmentId == null && apartments.length === 1) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- автоселект единственной квартиры после загрузки списка
      setApartmentId(apartments[0].apartment_id)
    }
  }, [apartments, apartmentId])

  const createMutation = useMutation<PassCreateResponse, unknown, void>({
    mutationFn: () =>
      twaClient
        .post<PassCreateResponse>(`${ACCESS_BASE}/passes`, {
          apartment_id: apartmentId,
          pass_type: passType,
          valid_until: new Date(validUntil).toISOString(),
          plate_number_original: plate.trim() || undefined,
          max_entries: 1,
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['twa', 'access', 'passes'] })
      // guest без номера → бэкенд вернул одноразовый код: показываем его
      // жителю один раз. Иначе — обычное подтверждение и возврат к списку.
      if (data.one_time_code) {
        setOneTimeCode(data.one_time_code)
        return
      }
      toast.success(t('twa.access.passNew.success'))
      navigate('/twa/app/access')
    },
    onError: (err: unknown) => {
      // 422 с detail.error === 'zone_not_resolved' → отдельная подсказка.
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      const isZone =
        detail && typeof detail === 'object' && (detail as { error?: string }).error === 'zone_not_resolved'
      if (isZone) {
        toast.error(t('twa.access.passNew.zoneError'))
        return
      }
      notifyError(err, t('twa.access.passNew.error'))
    },
  })

  const canSubmit =
    apartmentId != null && validUntil.trim().length > 0 && !createMutation.isPending

  async function copyCode() {
    if (!oneTimeCode) return
    try {
      await navigator.clipboard.writeText(oneTimeCode)
      setCopied(true)
      haptic('notification')
      toast.success(t('twa.access.passNew.code.copied'))
    } catch {
      toast.error(t('common.error'))
    }
  }

  // Экран успеха с одноразовым кодом гостя (§9.3): показывается ОДИН РАЗ.
  if (oneTimeCode) {
    return (
      <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col">
        <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
          {t('twa.access.passNew.code.title')}
        </h1>

        <div className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-6 text-center">
          <p className="text-[13px] text-gray-500 dark:text-gray-400 mb-3">
            {t('twa.access.passNew.code.label')}
          </p>
          <div
            data-testid="one-time-code"
            className="font-mono text-3xl font-bold tracking-[0.3em] text-gray-900 dark:text-gray-100 mb-5 select-all"
          >
            {oneTimeCode}
          </div>
          <button
            type="button"
            onClick={copyCode}
            className="w-full bg-emerald-500 text-white py-3 rounded-xl font-semibold active:scale-[0.98] transition-transform"
          >
            {copied ? t('twa.access.passNew.code.copied') : t('twa.access.passNew.code.copy')}
          </button>
        </div>

        <p className="mt-4 text-[13px] text-amber-600 dark:text-amber-400 text-center px-2">
          {t('twa.access.passNew.code.hint')}
        </p>

        <button
          type="button"
          onClick={() => navigate('/twa/app/access')}
          className="mt-auto w-full border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 py-3 rounded-xl font-semibold"
        >
          {t('twa.access.passNew.code.done')}
        </button>
      </div>
    )
  }

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <button onClick={() => navigate(-1)} className="text-[13px] text-emerald-500 mb-3">
        ← {t('common.back')}
      </button>
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
        {t('twa.access.passNew.title')}
      </h1>

      {apartmentsLoading && <p className="text-[13px] text-gray-400">{t('twa.access.loading')}</p>}

      {!apartmentsLoading && apartments.length === 0 && (
        <p className="text-[13px] text-gray-500 dark:text-gray-400">
          {t('twa.access.apartment.none')}
        </p>
      )}

      {!apartmentsLoading && apartments.length > 0 && (
        <div className="space-y-4">
          <ApartmentSelect apartments={apartments} value={apartmentId} onChange={setApartmentId} />

          <div>
            <label className="block text-[12px] text-gray-500 dark:text-gray-400 mb-1">
              {t('twa.access.passNew.type')}
            </label>
            <div className="grid grid-cols-3 gap-2">
              {RESIDENT_PASS_TYPES.map((pt) => (
                <button
                  key={pt}
                  type="button"
                  onClick={() => setPassType(pt)}
                  className={`rounded-xl p-2.5 text-[13px] border transition-transform active:scale-[0.97] ${
                    passType === pt
                      ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-400 dark:border-emerald-700'
                      : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                  }`}
                >
                  {t(`twa.access.passType.${pt}`)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-[12px] text-gray-500 dark:text-gray-400 mb-1">
              {t('twa.access.passNew.plateOptional')}
            </label>
            <input
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
              placeholder="01A123BC"
              className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] uppercase focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div>
            <label className="block text-[12px] text-gray-500 dark:text-gray-400 mb-1">
              {t('twa.access.passNew.validUntil')}
            </label>
            <input
              type="datetime-local"
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
              className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <button
            onClick={() => createMutation.mutate()}
            disabled={!canSubmit}
            className="w-full bg-emerald-500 text-white py-3 rounded-xl font-semibold disabled:opacity-50"
          >
            {createMutation.isPending ? t('common.loading') : t('twa.access.passNew.submit')}
          </button>
        </div>
      )}
    </div>
  )
}
