import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Car, PlusCircle } from 'lucide-react'
import { twaClient } from '../../twaClient'
import { CardSkeleton } from '../../components/Skeleton'
import PullToRefresh from '../../components/PullToRefresh'
import {
  ACCESS_BASE,
  formatDateTime,
  statusBadgeClass,
  type AccessPage,
  type RequestRow,
  type VehicleRow,
} from './types'

function StatusPill({ status, label }: { status: string; label: string }) {
  return (
    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${statusBadgeClass(status)}`}>
      {label}
    </span>
  )
}

export default function VehiclesTab() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const vehiclesQuery = useQuery<AccessPage<VehicleRow>>({
    queryKey: ['twa', 'access', 'vehicles'],
    queryFn: () => twaClient.get(`${ACCESS_BASE}/my/vehicles`).then((r) => r.data),
    staleTime: 30_000,
  })

  const requestsQuery = useQuery<AccessPage<RequestRow>>({
    queryKey: ['twa', 'access', 'requests'],
    queryFn: () => twaClient.get(`${ACCESS_BASE}/my/requests`).then((r) => r.data),
    staleTime: 30_000,
  })

  const vehicles = vehiclesQuery.data?.items ?? []
  const requests = requestsQuery.data?.items ?? []

  const vehicleStatusLabel = (s: string) => {
    const key = `twa.access.vehicleStatus.${s}`
    const translated = t(key)
    return translated === key ? s : translated
  }
  const requestStatusLabel = (s: string) => {
    const key = `twa.access.requestStatus.${s}`
    const translated = t(key)
    return translated === key ? s : translated
  }

  return (
    <PullToRefresh
      queryKeys={[
        ['twa', 'access', 'vehicles'],
        ['twa', 'access', 'requests'],
      ]}
    >
      <button
        onClick={() => navigate('/twa/app/access/vehicle-request')}
        className="w-full flex items-center justify-center gap-2 bg-emerald-500 text-white py-3 rounded-xl font-medium mb-4 active:scale-[0.98] transition-transform"
      >
        <PlusCircle size={18} />
        {t('twa.access.vehicles.requestButton')}
      </button>

      {vehiclesQuery.isError && (
        <p className="text-[13px] text-red-500 mb-3">{t('twa.access.error')}</p>
      )}

      {vehiclesQuery.isLoading && <CardSkeleton />}

      {!vehiclesQuery.isLoading && vehicles.length === 0 && (
        <div className="text-center py-8">
          <p className="text-gray-400 text-[14px]">{t('twa.access.vehicles.empty')}</p>
        </div>
      )}

      <div className="space-y-2">
        {vehicles.map((v) => (
          <div
            key={v.id}
            className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <Car size={16} className="text-emerald-500 shrink-0" />
                <span className="font-semibold text-[14px] text-gray-900 dark:text-gray-100 truncate">
                  {v.plate_number_original}
                </span>
              </div>
              <StatusPill status={v.status} label={vehicleStatusLabel(v.status)} />
            </div>
            {(v.brand || v.model || v.color) && (
              <p className="text-[12px] text-gray-500 dark:text-gray-400 mt-1">
                {[v.brand, v.model, v.color].filter(Boolean).join(' · ')}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Мои заявки на авто */}
      <h2 className="font-semibold text-[14px] text-gray-900 dark:text-gray-100 mt-6 mb-2">
        {t('twa.access.vehicles.myRequests')}
      </h2>

      {requestsQuery.isLoading && <CardSkeleton />}

      {!requestsQuery.isLoading && requests.length === 0 && (
        <p className="text-gray-400 text-[13px]">{t('twa.access.vehicles.requestsEmpty')}</p>
      )}

      <div className="space-y-2">
        {requests.map((r) => (
          <div
            key={r.id}
            className="bg-white dark:bg-gray-800 rounded-2xl p-3 border border-gray-100 dark:border-gray-700"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-[13px] text-gray-900 dark:text-gray-100 truncate">
                {r.plate_number_original || r.plate_number_normalized || '—'}
              </span>
              <StatusPill status={r.status} label={requestStatusLabel(r.status)} />
            </div>
            <p className="text-[11px] text-gray-400 mt-1">{formatDateTime(r.created_at)}</p>
            {r.review_comment && (
              <p className="text-[12px] text-gray-500 dark:text-gray-400 mt-1">{r.review_comment}</p>
            )}
          </div>
        ))}
      </div>
    </PullToRefresh>
  )
}
