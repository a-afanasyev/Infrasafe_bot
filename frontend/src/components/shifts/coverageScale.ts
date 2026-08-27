/**
 * Общая шкала «исполнителей в час» для карт покрытия смен — дневной
 * (ShiftCoverageHeatmap) и недельной (WeekCoverageHeatmap). Живёт отдельным
 * модулем: экспорт не-компонентов из файла компонента ломает Fast Refresh
 * (eslint react-refresh/only-export-components).
 */
export function coverageCellColor(count: number): string {
  if (count === 0) return 'rgba(239,68,68,0.3)'
  if (count <= 2) return 'rgba(245,158,11,0.4)'
  if (count <= 4) return 'rgba(var(--accent-rgb),0.35)'
  return 'rgba(var(--accent-rgb),0.65)'
}

export const COVERAGE_LEGEND = [
  { label: '0', color: 'rgba(239,68,68,0.3)' },
  { label: '1-2', color: 'rgba(245,158,11,0.4)' },
  { label: '3-4', color: 'rgba(var(--accent-rgb),0.35)' },
  { label: '5+', color: 'rgba(var(--accent-rgb),0.65)' },
]
