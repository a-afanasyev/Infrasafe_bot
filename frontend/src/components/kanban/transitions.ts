/**
 * Канбан: правила переходов статусов заявок.
 * Вынесено из KanbanBoard.tsx, чтобы файл-компонент экспортировал только
 * компонент (react-refresh/only-export-components).
 * Must mirror backend _REQUEST_VALID_TRANSITIONS exactly.
 */
import type { KanbanColumn as TColumn } from '../../hooks/useKanban'
import { FROZEN_STATUSES } from '../../constants'

// Statuses that require a modal before transitioning
export const MODAL_STATUSES = new Set(['В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Исполнено'])

export const KANBAN_STATUSES = new Set([
  'Новая', 'В работе', 'Закуп', 'Уточнение',
  'Выполнена', 'Исполнено', 'Возвращена', 'Принято', 'Отменена',
])

export const VALID_TRANSITIONS: Record<string, Set<string>> = {
  'Новая':     new Set(['В работе', 'Закуп', 'Уточнение', 'Отменена']),
  'В работе':  new Set(['Закуп', 'Уточнение', 'Выполнена', 'Отменена']),
  'Закуп':     new Set(['В работе', 'Уточнение', 'Отменена']),
  'Уточнение': new Set(['В работе', 'Отменена']),
  'Выполнена': new Set(['Исполнено', 'В работе']),
  'Исполнено': new Set(['Принято', 'В работе']),
  // PR7: возврат заявителем разбирает менеджер — в работу (доделать),
  // принять (возврат необоснован) или отменить. В «Возвращена» заявка попадает
  // только действием заявителя (APPLICANT_RETURN), не перетаскиванием.
  'Возвращена': new Set(['В работе', 'Принято', 'Отменена']),
  'Принято':   new Set(),
  'Отменена':  new Set(),
}

export function resolveTargetStatus(overId: string, columns: TColumn[]): string | null {
  if (KANBAN_STATUSES.has(overId)) return overId
  const col = columns.find(c => c.requests.some(r => r.request_number === overId))
  return col?.status ?? null
}

export function isTransitionAllowed(sourceStatus: string | undefined, targetStatus: string): boolean {
  if (!sourceStatus) return false
  if (sourceStatus === targetStatus) return false
  return VALID_TRANSITIONS[sourceStatus]?.has(targetStatus) ?? false
}

/**
 * Назначение исполнителя (canon MANAGER_ASSIGN) применимо ТОЛЬКО при взятии
 * заявки из «Новая» в работу. Из «Закуп»/«Уточнение»/«Выполнена»/«Исполнено»/
 * «Возвращена» «В работе» — это resume/return (MANAGER_PURCHASE_DONE /
 * CLARIFY_RESOLVED / MANAGER_RETURN_TO_WORK), которые executor_id НЕ принимают
 * (иначе backend → 422 «unexpected field 'executor_id'»). Из этих источников
 * переход коммитим напрямую, без модалки выбора исполнителя.
 */
export function inProgressNeedsExecutorModal(sourceStatus: string | undefined, hasExecutor: boolean): boolean {
  return sourceStatus === 'Новая' && !hasExecutor
}

export { FROZEN_STATUSES }
