import type { ResidentListItem } from '../../types/api'

type ToneInput = Pick<ResidentListItem, 'status' | 'phone' | 'apartments_count' | 'verification_status' | 'documents_submitted' | 'bot_blocked'>

/** Нажал /start и бросил: бот заводит pending-запись до развилки и контакта,
 *  поэтому без телефона и квартир это не заявка на проверку. */
export function isRegistrationIncomplete(r: Pick<ResidentListItem, 'status' | 'phone' | 'apartments_count'>) {
  return r.status === 'pending' && !r.phone && r.apartments_count === 0
}

export type ResidentTone = 'botBlocked' | 'incomplete' | 'submitted' | 'pending' | 'default'

/** Цвет карточки жителя — первое сработавшее правило (решение владельца 2026-11-05). */
export function residentTone(r: ToneInput): ResidentTone {
  if (r.bot_blocked) return 'botBlocked'
  if (isRegistrationIncomplete(r)) return 'incomplete'
  if (r.documents_submitted) return 'submitted' // флаг бэкенда: только pending/requested с документом
  if (r.status === 'pending') return 'pending'
  return 'default'
}

const TINT = (color: string, pct = 8) => `color-mix(in srgb, ${color} ${pct}%, var(--color-bg-card))`

/** Фон и контур по тону; одобренные — без цвета. Строка таблицы вместо
 *  контура рисует полосу слева (`toneRowStyle`). */
export const TONE_STYLE: Record<ResidentTone, { background?: string; borderColor?: string }> = {
  botBlocked: { background: TINT('var(--red)'), borderColor: 'var(--red)' },
  incomplete: { borderColor: 'var(--red)' },
  submitted: { background: TINT('var(--blue)', 18), borderColor: 'var(--blue)' }, // на 8% синий неотличим от белого
  pending: { background: TINT('var(--amber)', 14) }, // жёлтый на 8% теряется в тёмной теме
  default: {},
}

/** Фон строки таблицы. Контур у `<tr>` не рисуется — см. `toneEdgeStyle`. */
export function toneRowStyle(tone: ResidentTone): { background?: string } {
  return { background: TONE_STYLE[tone].background }
}

/** Контур тона в таблице — полоса слева на ПЕРВОЙ ячейке: box-shadow у
 *  самого `<tr>` при border-collapse рисуется не во всех браузерах. */
export function toneEdgeStyle(tone: ResidentTone): { boxShadow?: string } {
  const { borderColor } = TONE_STYLE[tone]
  return { boxShadow: borderColor ? `inset 3px 0 0 ${borderColor}` : undefined }
}
