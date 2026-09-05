import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { PaymentImport } from '@/types/paymentControl'
import { formatBusinessDate, formatInstant, formatMoney } from './format'

interface Props {
  report: PaymentImport
  account: string
  rowOffset: number
  reason: string
  isChanging: boolean
  onRowOffsetChange: (offset: number) => void
  onReasonChange: (reason: string) => void
  onChange: (action: 'activate' | 'deactivate') => void
}

const PAGE = 200

/** Предпросмотр строк импорта, активация/деактивация и журнал действий. */
export default function ImportDetailSection({
  report, account, rowOffset, reason, isChanging, onRowOffsetChange, onReasonChange, onChange,
}: Props) {
  const { t } = useTranslation()
  return (
    <section className="space-y-3 rounded-lg border border-border-default p-4">
      <h2 className="font-semibold">#{report.id} · {report.filename} · {t(`paymentControl.status.${report.status}`)}</h2>
      <p className="text-sm">
        {report.source} · {formatBusinessDate(report.as_of)} · {t('paymentControl.rows')}: {report.row_count}
        {' · '}{t('paymentControl.errors')}: {report.invalid}
      </p>
      <p className="text-xs text-text-muted">{t('paymentControl.previewLimit')}</p>
      <div className="max-h-80 overflow-auto">
        <table className="w-full text-left text-sm">
          <thead><tr>
            <th>{t('paymentControl.line')}</th>
            <th>{t('paymentControl.account')}</th>
            <th>{t('paymentControl.debt')} / {t('paymentControl.prepayment')}</th>
            <th>{t('paymentControl.amount')}</th>
            <th>{t('paymentControl.note')}</th>
            <th>{t('paymentControl.errors')}</th>
          </tr></thead>
          <tbody>{report.rows?.map(row => (
            <tr key={row.line} className={`border-t border-border-default ${row.account_number === account ? 'bg-accent/10' : ''}`}>
              <td className="py-2">{row.line}</td>
              <td>{row.account_number || row.raw?.account_number}</td>
              <td>{formatMoney(row.debt)} / {formatMoney(row.prepayment)}</td>
              <td>{formatMoney(row.amount)}</td>
              <td className="text-text-muted">{row.note || '—'}</td>
              <td className="text-red">{row.errors.join('; ')}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" disabled={!rowOffset} onClick={() => onRowOffsetChange(Math.max(0, rowOffset - PAGE))}>
          {t('paymentControl.previous')}
        </Button>
        <Button variant="outline" disabled={rowOffset + PAGE >= report.row_count} onClick={() => onRowOffsetChange(rowOffset + PAGE)}>
          {t('paymentControl.next')}
        </Button>
      </div>
      {report.status !== 'active'
        ? <Button disabled={!!report.invalid || isChanging} onClick={() => onChange('activate')}>{t('paymentControl.activate')}</Button>
        : <div className="flex gap-2">
            <Input aria-label={t('paymentControl.reason')} placeholder={t('paymentControl.reason')} value={reason}
                   onChange={e => onReasonChange(e.target.value)} maxLength={500} />
            <Button variant="outline" disabled={reason.trim().length < 3 || isChanging} onClick={() => onChange('deactivate')}>
              {t('paymentControl.deactivate')}
            </Button>
          </div>}
      <details><summary>{t('paymentControl.audit')}</summary>
        {report.audit?.map((event, i) => <p key={i} className="text-xs">
          {formatInstant(event.created_at)} · {t(`paymentControl.actions.${event.action}`)} · {t('paymentControl.actor')} {event.actor_id}
          {event.reason && ` · ${event.reason}`}
        </p>)}
      </details>
    </section>
  )
}
