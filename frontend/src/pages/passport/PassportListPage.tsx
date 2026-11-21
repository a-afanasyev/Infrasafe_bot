import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { usePageTitle } from '../../hooks/usePageTitle'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import EmptyState from '../../components/shared/EmptyState'
import { usePassports } from '../../features/passport/api'

/** Паспорта домов: дом плиткой — статус и сколько пунктов отвечено. */
export default function PassportListPage() {
  const { t } = useTranslation()
  usePageTitle(t('housePassport.title'))
  const list = usePassports()

  if (list.isLoading) return <LoadingSpinner />
  if (list.isError || !list.data?.length) {
    return <div className="p-6"><EmptyState icon="🏢" title={t(list.isError ? 'housePassport.errors.generic' : 'housePassport.empty')} /></div>
  }
  return (
    <div className="p-6 flex flex-col gap-5">
      <h1 className="text-xl font-semibold text-text-primary">{t('housePassport.title')}</h1>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {list.data.map((p) => {
          const pct = p.progress.total ? Math.round((p.progress.done / p.progress.total) * 100) : 0
          return (
            <Link key={p.building_id} to={`/dashboard/passports/${p.building_id}`}
                  className="flex flex-col gap-2 rounded-md border border-border-default bg-bg-card p-4 hover:bg-bg-card-hover">
              <span className="text-sm font-medium text-text-primary">{p.address}</span>
              <span className="text-[12px] text-text-muted">{t(`housePassport.status.${p.status}`)}</span>
              <progress className="w-full accent-[var(--accent)]" value={p.progress.done} max={p.progress.total || 1} aria-label={t('housePassport.progress')} />
              <span className="text-[12px] text-text-muted">{p.progress.done} / {p.progress.total} · {pct} %</span>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
