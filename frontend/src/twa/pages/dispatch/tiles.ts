// Экран диспетчера — те же размеры, что у простого режима исполнителя
// (twa/simple): плитка ≥ 64 px, текст ≥ 20 px, один вопрос на экран.
const TILE_BASE =
  'w-full min-h-[64px] px-4 py-3 rounded-2xl text-[20px] font-semibold text-left bg-white dark:bg-gray-800 border-2 active:scale-[0.98] transition-transform disabled:opacity-60'
const TILE_TEXT = 'text-gray-900 dark:text-gray-50'
// Тон задаёт цвет рамки целиком: два цвета рамки в одном классе спорили бы
// между собой, и подсветка не применялась.
const TILE_TONE = {
  plain: `${TILE_TEXT} border-gray-200 dark:border-gray-700`,
  selected: `${TILE_TEXT} border-emerald-600`,
  flagged: `${TILE_TEXT} border-amber-500`,
  danger: `${TILE_TEXT} border-red-400 dark:border-red-600`,
} as const

export const tile = (tone: keyof typeof TILE_TONE = 'plain'): string => `${TILE_BASE} ${TILE_TONE[tone]}`
export const TILE = tile()
/** Плитка «не конкретная квартира/дом» — отличается от списка объектов. */
export const TILE_WHOLE = `${TILE_BASE} border-dashed border-emerald-600 text-emerald-700 dark:text-emerald-300`
export const INPUT =
  'w-full px-4 rounded-2xl text-[22px] bg-white dark:bg-gray-800 border-2 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-50 focus:outline-none focus:border-emerald-600'
