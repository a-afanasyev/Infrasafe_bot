import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export type ImportKind = 'balances' | 'payments'

interface Props {
  kind: ImportKind
  source: string
  asOf: string
  file: File | null
  isPending: boolean
  onKindChange: (kind: ImportKind) => void
  onSourceChange: (source: string) => void
  onAsOfChange: (asOf: string) => void
  onFileChange: (file: File | null) => void
  onUpload: () => void
}

const LABEL_CLASS = 'flex flex-col gap-1 text-sm text-text-secondary'

/** Загрузка реестра: только предпросмотр, активация — отдельным подтверждением. */
export default function ImportUploadSection(props: Props) {
  const { t } = useTranslation()
  const { kind, source, asOf, file, isPending } = props
  return (
    <section className="space-y-3 rounded-lg border border-border-default p-4">
      <h2 className="font-semibold">{t('paymentControl.upload')}</h2>
      <div className="grid gap-3 md:grid-cols-3">
        <label className={LABEL_CLASS}>{t('paymentControl.kind')}
          <select className="rounded border border-border-default bg-bg-card p-2" value={kind}
                  onChange={e => props.onKindChange(e.target.value as ImportKind)}>
            <option value="balances">{t('paymentControl.balances')}</option>
            <option value="payments">{t('paymentControl.payments')}</option>
          </select>
        </label>
        <label className={LABEL_CLASS}>{t('paymentControl.source')}
          <Input value={source} maxLength={100} onChange={e => props.onSourceChange(e.target.value)} />
        </label>
        <label className={LABEL_CLASS}>{t('paymentControl.asOf')}
          <Input type="date" value={asOf} onChange={e => props.onAsOfChange(e.target.value)} />
        </label>
      </div>
      <p className="text-xs text-text-muted">{t('paymentControl.formatHint')}</p>
      <code className="block overflow-auto text-xs">
        {kind === 'balances' ? 'account_number;debt;prepayment' : 'account_number;operation_id;paid_at;amount'}
      </code>
      <label className={LABEL_CLASS}>CSV / XLSX
        <Input type="file" accept=".csv,.xlsx" onChange={e => props.onFileChange(e.target.files?.[0] || null)} />
      </label>
      <Button disabled={!file || !source.trim() || !asOf || isPending} onClick={props.onUpload}>
        {isPending ? t('common.loading') : t('paymentControl.preview')}
      </Button>
    </section>
  )
}
