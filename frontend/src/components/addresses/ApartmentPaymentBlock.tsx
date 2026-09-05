import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { apiClient } from '@/api/client'
import type { AccountBalance } from '@/types/paymentControl'

export default function ApartmentPaymentBlock({ apartmentId, accountNumber }: { apartmentId: number; accountNumber?: string | null }) {
  const { t } = useTranslation()
  const query = useQuery<AccountBalance>({
    queryKey: ['apartment-payment', apartmentId, accountNumber],
    queryFn: () => apiClient.get(`/api/v2/payment-control/apartments/${apartmentId}`).then(r => r.data),
    enabled: !!accountNumber,
    staleTime: 0,
    refetchInterval: 60_000,
    retry: false,
  })
  const current = !query.isError ? query.data?.current : null
  const params = new URLSearchParams()
  if (accountNumber) params.set('account', accountNumber)
  if (current) {
    params.set('import', String(current.import_id))
    params.set('offset', String(Math.floor((current.position ?? 0) / 200) * 200))
  }
  return <section className="mb-5 rounded-lg border border-border-default p-4 text-sm">
    <h3 className="mb-2 font-semibold">{t('paymentControl.title')}</h3>
    {!accountNumber ? <p className="mt-2 text-text-muted">{t('paymentControl.noAccount')}</p>
      : query.isLoading ? <p>{t('common.loading')}</p>
      : query.isError || query.data?.status === 'unavailable' ? <p role="status" className="mt-2 text-amber">{t('paymentControl.unavailable')}</p>
      : !current ? <p className="mt-2 text-text-muted">{t('paymentControl.noData')}</p>
      : <>
        <div className="my-2 grid grid-cols-2 gap-3">
          <div>{t('paymentControl.debt')}<strong className="block text-red">{current.debt} {current.currency}</strong></div>
          <div>{t('paymentControl.prepayment')}<strong className="block text-emerald">{current.prepayment} {current.currency}</strong></div>
        </div>
        <p className="text-xs text-text-muted">{t('paymentControl.asOf')}: {current.as_of} · {current.source} · {current.filename}</p>
      </>}
    <Link className="mt-3 inline-block text-accent underline" to={`/dashboard/payment-control?${params}`}>
      {t('paymentControl.verify')}
    </Link>
  </section>
}
