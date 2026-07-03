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
import { ACCESS_BASE, RELATION_TYPES, type RelationType } from './types'

/**
 * Форма «Заявка на постоянный авто» (POST /api/v1/access/requests).
 * Тело: { apartment_id, plate_number_original, relation_type?, brand?, model?, color? }.
 * Результат — заявка в статусе pending. apartment_id берётся из approved-квартир.
 */
export default function VehicleRequestPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic, showBackButton } = useTelegramSDK()

  const { data: apartments = [], isLoading: apartmentsLoading } = useApartments()

  const [apartmentId, setApartmentId] = useState<number | null>(null)
  const [plate, setPlate] = useState('')
  const [relation, setRelation] = useState<RelationType | ''>('')
  const [brand, setBrand] = useState('')
  const [model, setModel] = useState('')
  const [color, setColor] = useState('')

  // Telegram BackButton → назад в раздел.
  useEffect(() => showBackButton(() => navigate(-1)), [showBackButton, navigate])

  // Одна квартира → автоселект (выбор не нужен).
  useEffect(() => {
    if (apartmentId == null && apartments.length === 1) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- автоселект единственной квартиры после загрузки списка
      setApartmentId(apartments[0].apartment_id)
    }
  }, [apartments, apartmentId])

  const createMutation = useMutation({
    mutationFn: () =>
      twaClient.post(`${ACCESS_BASE}/requests`, {
        apartment_id: apartmentId,
        plate_number_original: plate.trim(),
        relation_type: relation || undefined,
        brand: brand.trim() || undefined,
        model: model.trim() || undefined,
        color: color.trim() || undefined,
      }),
    onSuccess: () => {
      haptic('notification')
      toast.success(t('twa.access.vehicleRequest.success'))
      queryClient.invalidateQueries({ queryKey: ['twa', 'access', 'requests'] })
      navigate('/twa/app/access')
    },
    onError: (err: unknown) => notifyError(err, t('twa.access.vehicleRequest.error')),
  })

  const canSubmit = apartmentId != null && plate.trim().length > 0 && !createMutation.isPending

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <button onClick={() => navigate(-1)} className="text-[13px] text-emerald-500 mb-3">
        ← {t('common.back')}
      </button>
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
        {t('twa.access.vehicleRequest.title')}
      </h1>

      {apartmentsLoading && (
        <p className="text-[13px] text-gray-400">{t('twa.access.loading')}</p>
      )}

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
              {t('twa.access.vehicleRequest.plate')}
            </label>
            <input
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
              placeholder={t('twa.access.vehicleRequest.platePlaceholder')}
              className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] uppercase focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div>
            <label className="block text-[12px] text-gray-500 dark:text-gray-400 mb-1">
              {t('twa.access.vehicleRequest.relation')}
            </label>
            <div className="grid grid-cols-2 gap-2">
              {RELATION_TYPES.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRelation(r)}
                  className={`rounded-xl p-2.5 text-[13px] border transition-transform active:scale-[0.97] ${
                    relation === r
                      ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-400 dark:border-emerald-700'
                      : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                  }`}
                >
                  {t(`twa.access.relation.${r}`)}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <input
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder={t('twa.access.vehicleRequest.brand')}
              className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-2.5 text-[13px] focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={t('twa.access.vehicleRequest.model')}
              className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-2.5 text-[13px] focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <input
              value={color}
              onChange={(e) => setColor(e.target.value)}
              placeholder={t('twa.access.vehicleRequest.color')}
              className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-2.5 text-[13px] focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <p className="text-[11px] text-gray-400">{t('twa.access.vehicleRequest.optional')}</p>

          <button
            onClick={() => createMutation.mutate()}
            disabled={!canSubmit}
            className="w-full bg-emerald-500 text-white py-3 rounded-xl font-semibold disabled:opacity-50"
          >
            {createMutation.isPending ? t('common.loading') : t('twa.access.vehicleRequest.submit')}
          </button>
        </div>
      )}
    </div>
  )
}
