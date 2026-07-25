/**
 * Канбан: цвета статусов заявок — единственная карта на дашборд.
 *
 * Раньше жила в двух копиях (`KanbanColumn.tsx` и `RequestDetailModal.tsx`);
 * копии разъехались на «Возвращена» (AUD5-APIFE-16). Ключ — `ApiStatus`, то
 * есть канон `STATUS_MAP` из `i18n/apiMaps`: новый статус на бэкенде уронит
 * `tsc -b` здесь, а не молча выдаст серый бейдж в проде.
 */
import type { ApiStatus } from '../../i18n/apiMaps'

/** Фон + цвет текста бейджа статуса. */
export const STATUS_BADGE: Record<ApiStatus, { bg: string; text: string }> = {
  'Новая':      { bg: 'bg-blue/12',      text: 'text-blue' },
  'В работе':   { bg: 'bg-amber/12',     text: 'text-[#d97706]' },
  'Закуп':      { bg: 'bg-violet/12',    text: 'text-violet' },
  'Уточнение':  { bg: 'bg-cyan/12',      text: 'text-cyan' },
  'Выполнена':  { bg: 'bg-emerald/12',   text: 'text-emerald' },
  'Исполнено':  { bg: 'bg-accent/12',    text: 'text-accent' },
  'Возвращена': { bg: 'bg-[#fb923c]/12', text: 'text-[#ea580c]' },
  'Принято':    { bg: 'bg-green/12',     text: 'text-green' },
  'Отменена':   { bg: 'bg-red/12',       text: 'text-red' },
}

/** Точка-индикатор статуса (колонки канбана, пункты меню переходов). */
export const STATUS_DOT: Record<ApiStatus, string> = {
  'Новая':      'bg-[#60a5fa]',
  'В работе':   'bg-[#fbbf24]',
  'Закуп':      'bg-[#a78bfa]',
  'Уточнение':  'bg-[#22d3ee]',
  'Выполнена':  'bg-[#34d399]',
  'Исполнено':  'bg-accent',
  'Возвращена': 'bg-[#fb923c]',
  'Принято':    'bg-[#4ade80]',
  'Отменена':   'bg-[#f87171]',
}
