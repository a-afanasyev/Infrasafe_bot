import { useState } from 'react'
import { useDebouncedValue } from './useDebouncedValue'
import { useEmployeesPage } from './useEmployees'
import type { EmployeeBrief } from '../types/api'

/** Сколько записей пикер берёт одной страницей — потолок серверного `limit`. */
export const PICKER_PAGE_LIMIT = 200

export type EmployeePickerFilters = Record<string, string | boolean | undefined>

/**
 * Данные для выпадающих списков и пикеров сотрудников (создание/перенос/
 * переназначение смен, удаление сотрудника, выбор исполнителя).
 *
 * AUD7-CODE-06: раньше эти места брали первые 50 записей без поиска — 51-го
 * сотрудника выбрать было нельзя. Пикер берёт широкую страницу (`PICKER_PAGE_LIMIT`)
 * и передаёт поиск серверу; если сотрудников больше страницы — `truncated`, и
 * компонент поля поиска просит уточнить запрос. Клиентские предикаты
 * («не текущий исполнитель», «только approved») остаются у потребителей.
 */
export function useEmployeePicker(filters: EmployeePickerFilters = {}) {
  const [search, setSearch] = useState('')
  const debounced = useDebouncedValue(search.trim())
  const query = useEmployeesPage(
    filters,
    debounced || undefined,
    { limit: PICKER_PAGE_LIMIT, offset: 0 },
  )
  const employees: EmployeeBrief[] = query.data?.items ?? []
  const total = query.data?.total ?? 0
  return {
    search,
    setSearch,
    employees,
    total,
    truncated: total > employees.length,
    isLoading: query.isLoading,
    isSuccess: query.isSuccess,
  }
}
