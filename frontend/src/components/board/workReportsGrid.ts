// Геометрия сетки плиток отчётов на табло и обрезка до полных рядов.
// Отдельный файл: модуль-компонент не должен экспортировать функции (react-refresh).
// Геометрия сетки плиток; по ней же считается, сколько плиток влезает в ряд.
export const MIN_CARD_PX = 170
export const GAP_PX = 18

// Сколько колонок даст `repeat(auto-fill, minmax(MIN_CARD_PX, 1fr))` при ширине w.
export function columnsFor(width: number): number {
  return Math.max(1, Math.floor((width + GAP_PX) / (MIN_CARD_PX + GAP_PX)))
}

// Только полные ряды: 8 плиток при 7 в ряду → 7, а не ряд + «сирота».
// Меньше одного ряда — показываем всё, что есть.
export function fullRows<T>(items: T[], cols: number): T[] {
  if (cols <= 0 || items.length <= cols) return items
  return items.slice(0, Math.floor(items.length / cols) * cols)
}
