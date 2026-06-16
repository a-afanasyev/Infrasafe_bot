import { describe, expect, it } from 'vitest'
import {
  isTransitionAllowed,
  VALID_TRANSITIONS,
  FROZEN_STATUSES,
  inProgressNeedsExecutorModal,
} from './KanbanBoard'

// Bug: дроп заявки из «Закуп» в «В работе» давал 422. «В работе» открывал
// модалку выбора исполнителя и слал executor_id, но из «Закуп»/«Уточнение»/
// «Выполнена»/«Исполнено»/«Возвращена» канон-действие — resume/return
// (MANAGER_PURCHASE_DONE / CLARIFY_RESOLVED / MANAGER_RETURN_TO_WORK), которое
// executor_id НЕ принимает. Модалка назначения нужна только из «Новая».
describe('inProgressNeedsExecutorModal (assign-executor only from «Новая»)', () => {
  it('opens the executor modal only for «Новая» → «В работе» without executor', () => {
    expect(inProgressNeedsExecutorModal('Новая', false)).toBe(true)
  })

  it('skips the modal for «Новая» when an executor is already set', () => {
    expect(inProgressNeedsExecutorModal('Новая', true)).toBe(false)
  })

  it('never opens the executor modal for resume/return sources (would 422)', () => {
    for (const src of ['Закуп', 'Уточнение', 'Выполнена', 'Исполнено', 'Возвращена']) {
      expect(inProgressNeedsExecutorModal(src, false)).toBe(false)
      expect(inProgressNeedsExecutorModal(src, true)).toBe(false)
    }
  })
})

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
