/**
 * Ячейки табличной вёрстки дашборда — общие для всех разделов.
 *
 * Раньше жили в `components/elevators/TableCells.tsx`; переехали сюда, когда
 * заголовки понадобились жителям и сотрудникам — импортировать разметку из
 * модуля лифтов в чужой раздел неверно. Прежний путь остался реэкспортом.
 */
import type { ReactNode } from 'react'

import { SortIndicator, type SortHeaderProps } from './SortIndicator'

const TH_CLASS =
  'px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)] whitespace-nowrap'

/**
 * Заголовок колонки. Без пропа `sort` рендерит ровно прежнюю статичную
 * ячейку — все существующие потребители не меняются. С `sort` заголовок
 * становится кнопкой, а состояние объявляется через `aria-sort`.
 */
export function Th({
  children,
  className = '',
  sort,
}: {
  children?: ReactNode
  className?: string
  sort?: SortHeaderProps
}) {
  if (!sort) {
    return <th className={`${TH_CLASS} ${className}`}>{children}</th>
  }
  return (
    <th className={`${TH_CLASS} ${className}`} aria-sort={sort.ariaSort}>
      <SortIndicator {...sort}>{children}</SortIndicator>
    </th>
  )
}

export function Td({ children, className = '' }: { children?: ReactNode; className?: string }) {
  return <td className={`px-3 py-2 text-[13px] text-text-primary ${className}`}>{children}</td>
}

export function TableShell({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
      <table className="w-full border-collapse">{children}</table>
    </div>
  )
}

export function HeadRow({ children }: { children: ReactNode }) {
  return <tr className="bg-bg-surface border-b border-border-default">{children}</tr>
}

export function BodyRow({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <tr className={`border-b border-border-default last:border-0 ${className}`}>{children}</tr>
}
