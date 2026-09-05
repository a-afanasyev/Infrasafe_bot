import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { apiClient } from '@/api/client'
import { usePageTitle } from '../hooks/usePageTitle'
import { todayInDisplayTz } from '../utils/timezone'
import { safeErrorMessage } from '@/utils/errorMessage'
import AccountLookupSection from '../components/payment/AccountLookupSection'
import ImportUploadSection, { type ImportKind } from '../components/payment/ImportUploadSection'
import ImportDetailSection from '../components/payment/ImportDetailSection'
import ImportHistorySection from '../components/payment/ImportHistorySection'
import type { AccountBalance, PaymentImport } from '@/types/paymentControl'

const BASE = '/api/v2/payment-control'
const ROW_PAGE = 200

export default function PaymentControlPage() {
  const { t } = useTranslation()
  usePageTitle(t('paymentControl.title'))
  const qc = useQueryClient()
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

  const imports = useQuery<PaymentImport[]>({
    queryKey: ['payment-imports', offset],
    queryFn: () => apiClient.get(`${BASE}/imports`, { params: { offset } }).then(r => r.data),
    retry: false,
  })
  const detail = useQuery<PaymentImport>({
    queryKey: ['payment-import', selectedId, rowOffset],
    queryFn: () => apiClient.get(`${BASE}/imports/${selectedId}`, { params: { offset: rowOffset } }).then(r => r.data),
    enabled: !!selectedId, retry: false,
  })
  const balance = useQuery<AccountBalance>({
    queryKey: ['payment-account', account],
    queryFn: () => apiClient.get(`${BASE}/account`, { params: { account_number: account } }).then(r => r.data),
    enabled: !!account, retry: false,
  })

  function selectImport(importId: number, position = 0) {
    const next = new URLSearchParams(params)
    const pageStart = Math.floor(position / ROW_PAGE) * ROW_PAGE
    next.set('import', String(importId))
    next.set('offset', String(pageStart))
    setRowOffset(pageStart)
    setParams(next)
    setReason('')
  }
  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['payment-imports'] }), qc.invalidateQueries({ queryKey: ['payment-import'] }),
      qc.invalidateQueries({ queryKey: ['payment-account'] }), qc.invalidateQueries({ queryKey: ['apartment-payment'] }),
    ])
  }
  const upload = useMutation({
    mutationFn: async () => {
      const body = new FormData()
      body.append('kind', kind); body.append('as_of', asOf); body.append('source', source.trim())
      if (file) body.append('file', file)
      return (await apiClient.post<PaymentImport>(`${BASE}/imports/preview`, body)).data
    },
    onSuccess: async data => { selectImport(data.id); await refresh() },
  })
  const change = useMutation({
    mutationFn: (action: 'activate' | 'deactivate') =>
      apiClient.post(`${BASE}/imports/${selectedId}/${action}`, action === 'deactivate' ? { reason: reason.trim() } : undefined),
    onSuccess: refresh,
  })
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
      onUpload={() => upload.mutate()}
    />
    {error && <p role="alert" className="text-red">{safeErrorMessage(error, t('paymentControl.error'))}</p>}
    {detail.data && !detail.isError && <ImportDetailSection
      report={detail.data} account={account} rowOffset={rowOffset} reason={reason} isChanging={change.isPending}
      onRowOffsetChange={setRowOffset} onReasonChange={setReason} onChange={action => change.mutate(action)}
    />}
    <ImportHistorySection imports={imports} offset={offset} onOffsetChange={setOffset} onSelectImport={selectImport} />
  </div>
}
