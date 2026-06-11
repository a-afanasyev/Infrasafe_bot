const STATUS_STYLES: Record<string, string> = {
  'Новая': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  'В работе': 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  'Закуп': 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
  'Уточнение': 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  'Выполнена': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  'Исполнено': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  'Возвращена': 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  'Принято': 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  'Отменена': 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
}

export default function StatusBadge({ status, label }: { status: string; label: string }) {
  const style = STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${style}`}>
      {label}
    </span>
  )
}
