/**
 * A9-P3-20: ЕДИНЫЙ канон цветов срочности заявки (карточка канбана и модалка
 * заявки). Раньше две копии уже разошлись: «Средняя» на карточке была сырым
 * `#d97706`, в модалке — токеном `text-amber`. Канон — токены темы там, где они
 * есть (оранжевого токена нет, поэтому `#ea580c`).
 *
 * TASK 17: канон-ключи + legacy-рус (dual-read, снять рус в Фазе 2).
 */
export interface UrgencyStyle {
  bg: string
  text: string
}

const LOW: UrgencyStyle = { bg: 'bg-emerald/12', text: 'text-emerald' }
const MEDIUM: UrgencyStyle = { bg: 'bg-amber/12', text: 'text-amber' }
const HIGH: UrgencyStyle = { bg: 'bg-[#ea580c]/12', text: 'text-[#ea580c]' }
const CRITICAL: UrgencyStyle = { bg: 'bg-red/12', text: 'text-red' }

const URGENCY_STYLES: Readonly<Record<string, UrgencyStyle>> = {
  low: LOW,
  medium: MEDIUM,
  high: HIGH,
  critical: CRITICAL,
  'Обычная': LOW,
  'Средняя': MEDIUM,
  'Срочная': HIGH,
  'Критическая': CRITICAL,
}

/** Стиль бейджа срочности; null — ключ неизвестен/пуст (бейдж не рисуем). */
export function getUrgencyStyle(urgency: string | null | undefined): UrgencyStyle | null {
  if (!urgency) return null
  return URGENCY_STYLES[urgency] ?? null
}
