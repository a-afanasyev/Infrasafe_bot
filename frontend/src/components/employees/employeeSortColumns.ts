/**
 * Колонки списка сотрудников: подпись + поле серверной сортировки.
 *
 * Сортируем сырые поля, а не содержимое ячеек: статус нарисован как «● Активен»
 * (первый символ у всех один), верификация — как «✓ Проверен» / «⏳ Ожидает»
 * (сортировка по эмодзи), смена — как «#10» (строкой «#10» меньше «#9»).
 *
 * «Специализация» без сортировки намеренно: это массив, полного порядка у него
 * нет. «Смена» ведёт себя как признак «на смене / нет» — по нему и упорядочиваем.
 */
import type { EmployeeBrief } from '../../types/api'
import type { SortableColumn } from '../../utils/tableSort'

export type EmployeeColumn = SortableColumn<EmployeeBrief> & { labelKey: string }

export const EMPLOYEE_COLUMNS: readonly EmployeeColumn[] = [
  { id: 'name', labelKey: 'employees.headerEmployee', kind: 'text', serverField: 'name' },
  { id: 'specialization', labelKey: 'employees.headerSpec', kind: 'text' },
  { id: 'verification', labelKey: 'employees.headerVerification', kind: 'enum', serverField: 'verification' },
  // «Статус» показывает «на смене / нет» — по этому признаку и упорядочиваем.
  { id: 'status', labelKey: 'employees.headerStatus', kind: 'enum', serverField: 'shift' },
  // «Смена» рисует номер текущей смены. Сортировать по нему нечего: тот же
  // признак «на смене» уже даёт соседняя колонка, а порядок номеров смен
  // ничего не значит для менеджера.
  { id: 'shift', labelKey: 'employees.headerShift', kind: 'number' },
  { id: 'actions', labelKey: 'employees.headerActions', kind: 'text' },
]

export const EMPLOYEES_SORT_STORAGE_KEY = 'employees_sort_v1'
