import { useTranslation } from 'react-i18next'
import { tStatus } from '../../i18n/apiMaps'

interface TimelineItem {
  status: string
  timestamp: string
  isCurrent?: boolean
}

interface Props {
  items: TimelineItem[]
}

const STATUS_COLORS: Record<string, string> = {
  'Новая': '#3b82f6',
  'В работе': '#8b5cf6',
  'Закуп': '#06b6d4',
  'Уточнение': '#f59e0b',
  'Выполнена': '#10b981',
  'Исполнено': '#10b981',
  'Принято': '#22c55e',
  'Отменена': '#6b7280',
}

export default function Timeline({ items }: Props) {
  const { t } = useTranslation()

  if (items.length === 0) return null

  return (
    <div className="relative pl-6">
      {/* Vertical line */}
      <div className="absolute left-[9px] top-2 bottom-2 w-0.5 bg-gray-200 dark:bg-gray-700" />

      {items.map((item, i) => {
        const color = STATUS_COLORS[item.status] ?? '#6b7280'
        const date = new Date(item.timestamp)
        const isLast = i === items.length - 1

        return (
          <div key={i} className={`relative pb-4 ${isLast ? 'pb-0' : ''}`}>
            {/* Dot */}
            <div
              className={`absolute left-[-15px] top-1 w-[12px] h-[12px] rounded-full border-2 ${
                item.isCurrent ? 'scale-125' : ''
              }`}
              style={{
                borderColor: color,
                backgroundColor: item.isCurrent ? color : 'transparent',
              }}
            />

            {/* Content */}
            <div className="ml-2">
              <div className="flex items-center gap-2">
                <span
                  className="text-[12px] font-semibold"
                  style={{ color }}
                >
                  {tStatus(item.status, t)}
                </span>
                {item.isCurrent && (
                  <span className="text-[10px] bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 px-1.5 py-0.5 rounded-full">
                    {t('twa.timeline.current') ?? 'текущий'}
                  </span>
                )}
              </div>
              <span className="text-[11px] text-gray-400">
                {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
