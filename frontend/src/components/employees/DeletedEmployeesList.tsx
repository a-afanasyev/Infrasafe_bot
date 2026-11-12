import { useTranslation } from 'react-i18next'
import LoadingSpinner from '../shared/LoadingSpinner'
import { useDeletedEmployees } from '../../hooks/useEmployees'
import { formatDateTime } from '../../utils/accessFormat'

/**
 * Удалённые сотрудники — только просмотр: кто, когда и почему удалил.
 * Восстановление — в боте (управление сотрудниками → «Удалённые»): человек
 * возвращается в очередь одобрения.
 */
export default function DeletedEmployeesList() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useDeletedEmployees()

  if (isLoading) return <LoadingSpinner />
  if (isError) return <div className="text-sm text-red">{t('employees.deleted.loadError')}</div>
  if (!data || data.length === 0) {
    return <div className="text-sm text-text-muted py-6">{t('employees.deleted.empty')}</div>
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[12px] text-text-muted">{t('employees.deleted.hint')}</div>
      <div className="bg-bg-card border border-border-default rounded-default overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-left text-[11px] uppercase text-text-muted border-b border-border-default">
              <th className="px-4 py-2 font-semibold">{t('employees.deleted.name')}</th>
              <th className="px-4 py-2 font-semibold">{t('employees.deleted.roles')}</th>
              <th className="px-4 py-2 font-semibold">{t('employees.deleted.when')}</th>
              <th className="px-4 py-2 font-semibold">{t('employees.deleted.by')}</th>
              <th className="px-4 py-2 font-semibold">{t('employees.deleted.reason')}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.id} className="border-b border-border-default last:border-b-0">
                <td className="px-4 py-2 text-text-primary font-medium">{row.full_name}</td>
                <td className="px-4 py-2 text-text-secondary">
                  {row.roles.map((r) => t(`rbac.roleTitles.${r}`, { defaultValue: r })).join(', ')}
                </td>
                <td className="px-4 py-2 text-text-secondary whitespace-nowrap">{formatDateTime(row.deleted_at)}</td>
                <td className="px-4 py-2 text-text-secondary">{row.deleted_by_name ?? '—'}</td>
                <td className="px-4 py-2 text-text-secondary">{row.deletion_reason ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
