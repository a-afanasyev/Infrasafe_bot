import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { UseQueryResult } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { isValidationError, safeErrorMessage } from '@/utils/errorMessage'
import type { AccountBalance } from '@/types/paymentControl'
import { formatBusinessDate, formatMoney } from './format'

interface Props {
  account: string
  balance: UseQueryResult<AccountBalance>
  onSearch: (account: string) => void
  onRefresh: () => void
  onSelectImport: (importId: number, position?: number) => void
}

/** Сверка одного лицевого счёта: текущий снимок, история снимков и платежи. */
export default function AccountLookupSection({ account, balance, onSearch, onRefresh, onSelectImport }: Props) {
  const { t } = useTranslation()
  const [search, setSearch] = useState(account)
  const data = balance.data
  return (
    <section className="space-y-3 rounded-lg border border-border-default p-4">
      <h2 className="font-semibold">{t('paymentControl.verify')}</h2>
      <form className="flex gap-2" onSubmit={e => { e.preventDefault(); onSearch(search.trim()) }}>
        <Input aria-label={t('paymentControl.account')} value={search} maxLength={64}
               onChange={e => setSearch(e.target.value)} placeholder={t('paymentControl.account')} />
        <Button type="submit" disabled={!search.trim()}>{t('paymentControl.find')}</Button>
        <Button type="button" variant="outline" onClick={onRefresh}>{t('paymentControl.refresh')}</Button>
      </form>
      {balance.isLoading && account && <p>{t('common.loading')}</p>}
      {balance.isError && (
        isValidationError(balance.error)
          ? <p role="alert" className="text-red">{safeErrorMessage(balance.error, t('paymentControl.error'))}</p>
          : <p role="alert" className="text-amber">{t('paymentControl.unavailable')}</p>
      )}
      {data && !balance.isError && <>
        <p className="text-sm font-semibold">{t('paymentControl.account')}: {account}</p>
        {data.current ? <div className="rounded border border-border-default p-3">
          <p>
            {t('paymentControl.debt')}: <strong className="text-red">{formatMoney(data.current.debt, data.current.currency)}</strong>
            {' · '}{t('paymentControl.prepayment')}: <strong className="text-emerald">{formatMoney(data.current.prepayment, data.current.currency)}</strong>
          </p>
          <p className="text-sm text-text-muted">{t('paymentControl.asOf')}: {formatBusinessDate(data.current.as_of)} · {data.current.source}</p>
          <Button variant="link" onClick={() => onSelectImport(data.current!.import_id, data.current!.position)}>
            {data.current.filename} · {t('paymentControl.line')} {data.current.line}
          </Button>
        </div> : <p>{t('paymentControl.noData')}</p>}
        {!!data.history?.length && <details><summary className="cursor-pointer">{t('paymentControl.balanceHistory')}</summary>
          {data.history.map(row => <div key={row.import_id} className="py-1 text-sm">
            <Button variant="link" onClick={() => onSelectImport(row.import_id)}>{formatBusinessDate(row.as_of)} · {row.source}</Button>
            {' '}{formatMoney(row.debt)} / {formatMoney(row.prepayment, row.currency)}
          </div>)}
        </details>}
        <details><summary className="cursor-pointer">{t('paymentControl.payments')}</summary>
          <p className="my-2 text-xs text-text-muted">{t('paymentControl.paymentHint')}</p>
          {data.payments?.map(row => <div key={`${row.source}:${row.operation_id}`} className="py-1 text-sm">
            {formatBusinessDate(row.paid_at)} · {row.operation_id} · {formatMoney(row.amount, row.currency)}
            {' '}<Button variant="link" onClick={() => onSelectImport(row.import_id)}>{row.source}</Button>
            {row.note && <span className="text-text-muted"> · {row.note}</span>}
          </div>)}
          {!data.payments?.length && <p className="text-sm">{t('paymentControl.noPayments')}</p>}
        </details>
      </>}
    </section>
  )
}
