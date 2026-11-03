import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { formatDate } from '../../i18n/formatters'
import { useAccountOwnersSummary, useImportAccountOwners } from '../../hooks/useAddresses'

/** Загрузка владельцев лицевых счетов из Mening Uyim — источник подсказки в очереди. */
export default function AccountOwnersImport() {
  const { t } = useTranslation()
  const input = useRef<HTMLInputElement>(null)
  const { data } = useAccountOwnersSummary()
  const upload = useImportAccountOwners()

  return (
    <div className="bg-bg-card border border-border-default rounded-default p-3 px-5 flex items-center gap-3 flex-wrap">
      <span className="text-[13px] text-text-secondary">
        {data?.total
          ? t('accountOwners.summary', {
              total: data.total,
              linked: data.linked,
              date: data.imported_at ? formatDate(data.imported_at, { dateStyle: 'short' }) : '—',
            })
          : t('accountOwners.empty')}
      </span>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        data-testid="account-owners-file"
        onChange={e => {
          const file = e.target.files?.[0]
          if (file) upload.mutate(file)
          e.target.value = ''
        }}
      />
      <Button
        variant="outline"
        size="sm"
        className="ml-auto"
        disabled={upload.isPending}
        onClick={() => input.current?.click()}
      >
        {t('accountOwners.upload')}
      </Button>
    </div>
  )
}
