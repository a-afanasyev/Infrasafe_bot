import { useTranslation } from 'react-i18next'
import { tCategory, tStatus } from '../../i18n/apiMaps'
import StatusBadge from './StatusBadge'

interface Props {
  requestNumber: string
  status: string
  category: string
  description?: string | null
  executorName?: string | null
  createdAt: string
  onClick?: () => void
}

export default function RequestCard({ requestNumber, status, category, description, executorName, createdAt, onClick }: Props) {
  const { t } = useTranslation()
  const date = new Date(createdAt)
  const dateStr = `${date.getDate().toString().padStart(2, '0')}.${(date.getMonth() + 1).toString().padStart(2, '0')}`

  return (
    <div
      onClick={onClick}
      className="bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-2xl p-3.5 mb-2 active:scale-[0.98] transition-transform cursor-pointer"
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-mono text-[11px] text-gray-400">{requestNumber}</span>
        <StatusBadge status={status} label={tStatus(status, t)} />
      </div>
      <div className="font-semibold text-[14px] text-gray-900 dark:text-gray-100 mb-0.5">
        {tCategory(category, t)}
      </div>
      {description && (
        <p className="text-[12px] text-gray-500 dark:text-gray-400 line-clamp-2">{description}</p>
      )}
      <div className="flex items-center justify-between mt-2 text-[11px] text-gray-400">
        {executorName && <span>👤 {executorName}</span>}
        <span className="ml-auto">{dateStr}</span>
      </div>
    </div>
  )
}
