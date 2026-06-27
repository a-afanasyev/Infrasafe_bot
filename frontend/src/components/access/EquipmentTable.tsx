import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import EmptyState from '../shared/EmptyState'
import { Button } from '@/components/ui/button'

/**
 * Универсальная таблица раздела «Оборудование» (зоны/въезды/камеры/шлагбаумы/
 * контроллеры). Колонки задаются декларативно (`columns`), действия в строке
 * («Изменить» / «Деактивировать») — опционально и только для прав на управление.
 *
 * Намеренно generic (в отличие от bespoke-таблиц базы доступа): пять ресурсов с
 * однотипной структурой строк, дублировать вёрстку пять раз — лишний код.
 */
export interface EquipmentColumn<T> {
  key: string
  label: string
  render: (row: T) => React.ReactNode
}

interface Props<T extends { id: number; is_active?: boolean }> {
  rows: T[]
  columns: EquipmentColumn<T>[]
  emptyText: string
  emptyIcon?: string
  onEdit?: (row: T) => void
  onDeactivate?: (row: T) => void
  /** Доп. действия в строке (напр. «Ротировать ключ» у контроллеров). */
  extraActions?: (row: T) => React.ReactNode
}

function HeaderCell({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)] whitespace-nowrap">
      {children}
    </th>
  )
}

export default function EquipmentTable<T extends { id: number; is_active?: boolean }>({
  rows,
  columns,
  emptyText,
  emptyIcon = '🧩',
  onEdit,
  onDeactivate,
  extraActions,
}: Props<T>) {
  const { t } = useTranslation()
  const hasActions = Boolean(onEdit || onDeactivate || extraActions)

  if (rows.length === 0) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
        <EmptyState icon={emptyIcon} title={emptyText} />
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-surface border-b border-border-default">
            {columns.map((c) => (
              <HeaderCell key={c.key}>{c.label}</HeaderCell>
            ))}
            {hasActions && <HeaderCell>{t('common.actions')}</HeaderCell>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const isLast = idx === rows.length - 1
            return (
              <tr
                key={row.id}
                className={cn(
                  'transition-colors duration-100',
                  !isLast && 'border-b border-border-default',
                )}
              >
                {columns.map((c) => (
                  <td key={c.key} className="px-3 py-2.5 text-[13px] text-text-primary">
                    {c.render(row)}
                  </td>
                ))}
                {hasActions && (
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap gap-1.5">
                      {onEdit && (
                        <Button size="sm" variant="outline" onClick={() => onEdit(row)}>
                          {t('common.edit')}
                        </Button>
                      )}
                      {extraActions?.(row)}
                      {onDeactivate && row.is_active !== false && (
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => onDeactivate(row)}
                        >
                          {t('accessControl.equipment.deactivate')}
                        </Button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
