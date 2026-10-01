import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { usePageTitle } from '../hooks/usePageTitle'
import { todayInDisplayTz } from '../utils/timezone'
import { safeErrorMessage } from '@/utils/errorMessage'
import AccountLookupSection from '../components/payment/AccountLookupSection'
import ImportUploadSection, { type ImportKind } from '../components/payment/ImportUploadSection'
import ImportDetailSection from '../components/payment/ImportDetailSection'
import ImportHistorySection from '../components/payment/ImportHistorySection'
import {
  useChangePaymentImport,
  usePaymentAccount,
  usePaymentImport,
  usePaymentImports,
  useRefreshPaymentControl,
  useUploadPaymentImport,
} from '../hooks/usePaymentControl'

const ROW_PAGE = 200

export default function PaymentControlPage() {
  const { t } = useTranslation()
  usePageTitle(t('paymentControl.title'))
  const [params, setParams] = useSearchParams()
  const account = params.get('account') || ''
  const selectedId = Number(params.get('import')) || null
  const [rowOffset, setRowOffset] = useState(Math.max(0, Number(params.get('offset')) || 0))
  const [kind, setKind] = useState<ImportKind>('balances')
  const [source, setSource] = useState('Accounting')
  // Дата состояния — календарное «сегодня» в бизнес-зоне: с UTC-датой ночная
  // выгрузка получала вчерашний as_of и проигрывала более старому снимку.
  const [asOf, setAsOf] = useState(todayInDisplayTz())
  const [file, setFile] = useState<File | null>(null)
  const [reason, setReason] = useState('')
  const [offset, setOffset] = useState(0)

  const imports = usePaymentImports(offset)
  const detail = usePaymentImport(selectedId, rowOffset)
  const balance = usePaymentAccount(account)

  function selectImport(importId: number, position = 0) {
    const next = new URLSearchParams(params)
    const pageStart = Math.floor(position / ROW_PAGE) * ROW_PAGE
    next.set('import', String(importId))
    next.set('offset', String(pageStart))
    setRowOffset(pageStart)
    setParams(next)
    setReason('')
  }
  const refresh = useRefreshPaymentControl()
  const upload = useUploadPaymentImport(async data => { selectImport(data.id); await refresh() })
  const change = useChangePaymentImport(refresh)
  const error = upload.error || change.error || detail.error

  return <div className="space-y-5 p-4 md:p-6">
    <div>
      <h1 className="text-xl font-semibold">{t('paymentControl.title')}</h1>
      <p className="mt-1 text-sm text-text-muted">{t('paymentControl.intro')}</p>
    </div>
    <AccountLookupSection
      account={account} balance={balance} onRefresh={() => void refresh()} onSelectImport={selectImport}
      onSearch={value => { const next = new URLSearchParams(params); next.set('account', value); setParams(next) }}
    />
    <ImportUploadSection
      kind={kind} source={source} asOf={asOf} file={file} isPending={upload.isPending}
      onKindChange={setKind} onSourceChange={setSource} onAsOfChange={setAsOf} onFileChange={setFile}
      onUpload={() => upload.mutate({ kind, asOf, source, file })}
    />
    {error && <p role="alert" className="text-red">{safeErrorMessage(error, t('paymentControl.error'))}</p>}
    {detail.data && !detail.isError && <ImportDetailSection
      report={detail.data} account={account} rowOffset={rowOffset} reason={reason} isChanging={change.isPending}
      onRowOffsetChange={setRowOffset} onReasonChange={setReason} onChange={action => change.mutate({ importId: selectedId, action, reason })}
    />}
    <ImportHistorySection imports={imports} offset={offset} onOffsetChange={setOffset} onSelectImport={selectImport} />
  </div>
}
