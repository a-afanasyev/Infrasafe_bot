import { useTranslation } from 'react-i18next'
import type { UseQueryResult } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import type { PaymentImport } from '@/types/paymentControl'
import { formatBusinessDate } from './format'

interface Props {
  imports: UseQueryResult<PaymentImport[]>
  offset: number
  onOffsetChange: (offset: number) => void
  onSelectImport: (importId: number) => void
}

const PAGE = 50

/** История импортов: постранично, по 50 записей. */
export default function ImportHistorySection({ imports, offset, onOffsetChange, onSelectImport }: Props) {
  const { t } = useTranslation()
  return (
    <section className="space-y-3">
      <h2 className="font-semibold">{t('paymentControl.importHistory')}</h2>
      {imports.isLoading && <p>{t('common.loading')}</p>}
      {imports.isError && <p role="alert" className="text-amber">{t('paymentControl.unavailable')}</p>}
      {imports.data?.map(row => (
        <button key={row.id} onClick={() => onSelectImport(row.id)}
                className="block w-full rounded border border-border-default p-3 text-left text-sm hover:bg-accent/10">
          #{row.id} · {row.filename} · {formatBusinessDate(row.as_of)} · {t(`paymentControl.status.${row.status}`)} · {row.row_count}
        </button>
      ))}
      <div className="flex gap-2">
        <Button variant="outline" disabled={!offset} onClick={() => onOffsetChange(Math.max(0, offset - PAGE))}>
          {t('paymentControl.previous')}
        </Button>
        <Button variant="outline" disabled={(imports.data?.length || 0) < PAGE} onClick={() => onOffsetChange(offset + PAGE)}>
          {t('paymentControl.next')}
        </Button>
      </div>
    </section>
  )
}
