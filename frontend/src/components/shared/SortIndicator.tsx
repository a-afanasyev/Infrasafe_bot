/**
 * Кнопка сортировки внутри заголовка колонки.
 *
 * Намеренно НЕ знает про `<th>`: часть таблиц дашборда собрана на настоящей
 * `<table>`, часть — на div + CSS-grid (адреса). Обёртку каждая разметка
 * ставит свою, а состояние объявляет через `aria-sort` на ячейке заголовка.
 */
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { SortDirection } from '../../utils/tableSort'

export interface SortHeaderProps {
  /** Направление этой колонки; `null` — сортировка сейчас по другой колонке. */
  direction: SortDirection | null
  onToggle: () => void
  /** Значение `aria-sort` для ячейки заголовка. */
  ariaSort: 'ascending' | 'descending' | 'none'
}

interface Props extends SortHeaderProps {
  /** Подпись колонки. Она же — доступное имя кнопки. */
  children?: ReactNode
}

const ICON = { asc: ArrowUp, desc: ArrowDown } as const

/**
 * Доступное имя кнопки — ровно подпись колонки, без добавок: подписи статусов
 * пересчитываются в тестах, и лишнее вхождение текста их ломает. Текущее
 * состояние несёт `aria-sort` на ячейке, следующее действие — `title`.
 */
export function SortIndicator({ direction, onToggle, children }: Props) {
  const { t } = useTranslation()
  const Icon = direction ? ICON[direction] : ChevronsUpDown
  const nextHint = !direction
    ? t('common.sort.nextAsc')
    : direction === 'asc'
      ? t('common.sort.nextDesc')
      : t('common.sort.nextReset')

  // Кнопка приносит свой шрифт и отступы — сбрасываем на унаследованные,
  // иначе шапка визуально прыгнет во всех таблицах сразу.
  return (
    <button
      type="button"
      onClick={onToggle}
      title={nextHint}
      // Браузер сбрасывает кнопке шрифт, регистр и межбуквенный интервал —
      // без явного наследования сортируемый заголовок выглядел бы иначе, чем
      // соседний обычный (проверено вживую: `text-transform` у кнопки `none`).
      className="inline-flex w-full cursor-pointer items-center gap-1 bg-transparent p-0 text-left [font:inherit] [letter-spacing:inherit] [text-transform:inherit] [color:inherit] hover:text-text-primary"
    >
      {children}
      <Icon size={12} aria-hidden className={direction ? 'text-text-primary' : 'opacity-40'} />
    </button>
  )
}
