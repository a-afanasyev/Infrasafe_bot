import { describe, expect, it } from 'vitest'
import { isTransitionAllowed, VALID_TRANSITIONS, FROZEN_STATUSES } from './KanbanBoard'

// PR7: «Возвращена» — канон-статус возврата заявителем. Менеджер на канбане
// разбирает возврат: в работу (доделать), принять (возврат необоснован) или
// отменить. Зеркалит backend action-table (MANAGER_RETURN_TO_WORK /
// MANAGER_FORCE_ACCEPT / CANCEL из «Возвращена»).
describe('KanbanBoard «Возвращена» transitions (PR7)', () => {
  it('manager may move a returned request to work / approved / cancelled', () => {
    expect(isTransitionAllowed('Возвращена', 'В работе')).toBe(true)
    expect(isTransitionAllowed('Возвращена', 'Принято')).toBe(true)
    expect(isTransitionAllowed('Возвращена', 'Отменена')).toBe(true)
  })

  it('returned has no nonsensical edges back into the open pipeline', () => {
    expect(isTransitionAllowed('Возвращена', 'Закуп')).toBe(false)
    expect(isTransitionAllowed('Возвращена', 'Уточнение')).toBe(false)
    expect(isTransitionAllowed('Возвращена', 'Выполнена')).toBe(false)
  })

  it('«Возвращена» is a known transition source but not frozen', () => {
    expect(VALID_TRANSITIONS['Возвращена']).toBeDefined()
    expect(FROZEN_STATUSES.has('Возвращена')).toBe(false)
  })
})
