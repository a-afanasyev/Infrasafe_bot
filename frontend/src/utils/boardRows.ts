import type { ModuleWidth } from '../types/boardConfig'

/**
 * Группирует блоки табло в строки для рендера:
 *  - два соседних `half` → пара (одна строка, 2 колонки);
 *  - `full` (или отсутствие width) или одиночный `half` без соседа-`half` →
 *    строка на всю ширину (никаких полупустых рядов).
 * Порядок сохраняется. Скрытые/пустые блоки нужно отфильтровать ДО вызова.
 */
export function groupBoardRows<T extends { width?: ModuleWidth }>(items: T[]): T[][] {
  const rows: T[][] = []
  let i = 0
  while (i < items.length) {
    const cur = items[i]
    const next = items[i + 1]
    if (cur.width === 'half' && next?.width === 'half') {
      rows.push([cur, next])
      i += 2
    } else {
      rows.push([cur])
      i += 1
    }
  }
  return rows
}
