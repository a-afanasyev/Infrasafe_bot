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
  if (r.documents_submitted && r.verification_status === 'requested') return 'submitted'
  if (r.status === 'pending') return 'pending'
  return 'default'
}
